print("HELLO! THE BACKEND IS STARTING (GOLDEN SYNC FINAL)!")
import sys
import os
import time
import threading
import signal
from datetime import datetime
import pytz

from config import app, db, socketio
from models import PlantStageStatus, PlantPreset, SensorLimits, PHData, TDSData, TemperatureHumidityData
import hal

from routes import *
from sensors import fetch_ph, fetch_tds, fetch_th, log_event, live_ph_data, live_tds_data, live_th_data
from dosing import check_and_adjust_sensors
from camera_ml import camera_worker, generate_timelapse, start_plant_monitor

def signal_handler(sig, frame):
    print("DEBUG: Shutting down backend...")
    log_event("SYSTEM_SHUTDOWN", "SYSTEM", "Controller service shutdown requested.")
    hal.cleanup()
    sys.exit(0)

# --- BACKGROUND THREADS ---

def fetch_loop():
    while True:
        try:
            with app.test_request_context():
                from sensors import get_water_temp
                w_t = get_water_temp()
                ph_res = fetch_ph(w_t)
                tds_res = fetch_tds(w_t)
                th_res = fetch_th()
                
                socketio.emit('telemetry_update', {
                    'ph': ph_res.get('ph_value'),
                    'ec': tds_res.get('tds_value'),
                    'temperature': th_res.get('temperature'),
                    'humidity': th_res.get('humidity')
                })
                
                check_and_adjust_sensors()
                process_status_mail_check()
        except Exception as e:
            import traceback
            print(f"CRITICAL ERROR in fetch_loop: {e}")
            traceback.print_exc()
        time.sleep(2)


def aggregation_loop():
    while True:
        time.sleep(600)
        try:
            with app.app_context():
                if live_ph_data:
                    avg_ph = round(sum(d["value"] for d in live_ph_data) / len(live_ph_data), 2)
                    avg_w_temp = round(sum(d.get("water_temp", 25.0) for d in live_ph_data) / len(live_ph_data), 2)
                    avg_a_temp = round(sum(d.get("air_temp", 25.0) for d in live_ph_data) / len(live_ph_data), 2)
                    db.session.add(PHData(ph_value=avg_ph, water_temp=avg_w_temp, air_temp=avg_a_temp))
                if live_tds_data:
                    avg_tds = round(sum(d["value"] for d in live_tds_data) / len(live_tds_data), 2)
                    avg_w_temp = round(sum(d.get("water_temp", 25.0) for d in live_tds_data) / len(live_tds_data), 2)
                    avg_a_temp = round(sum(d.get("air_temp", 25.0) for d in live_tds_data) / len(live_tds_data), 2)
                    db.session.add(TDSData(tds_value=avg_tds, water_temp=avg_w_temp, air_temp=avg_a_temp))
                if live_th_data:
                    avg_t = round(sum(d["t"] for d in live_th_data) / len(live_th_data), 2)
                    avg_h = round(sum(d["h"] for d in live_th_data) / len(live_th_data), 2)
                    db.session.add(TemperatureHumidityData(temperature=avg_t, humidity=avg_h))
                db.session.commit()
                print("DEBUG: 10-Minute Data Aggregation Committed to DB.")
        except Exception as e:
            print(f"DEBUG: aggregation_loop failed: {e}")

def daily_digest_loop():
    while True:
        try:
            now = datetime.now(pytz.timezone('Asia/Kolkata'))
            if now.hour == 2 and now.minute == 0:
                print("DEBUG: Auto-generating time-lapse at 2:00 AM")
                generate_timelapse()
                time.sleep(65)
                
            if now.hour == 8 and now.minute == 0:
                print("DEBUG: Sending Daily Digest at 8:00 AM")
                with app.test_client() as client: client.post('/send_report_email')
                time.sleep(65)
        except Exception as e: print(f"Daily digest error: {e}")
        time.sleep(30)

def run_migrations():
    from sqlalchemy import text
    try:
        db.session.execute(text("SELECT water_temp, air_temp FROM tds_data LIMIT 1"))
        print("DEBUG MIGRATION: tds_data already contains temperature columns.")
    except Exception:
        print("DEBUG MIGRATION: Migrating tds_data table...")
        db.session.rollback()
        try:
            db.session.execute(text("ALTER TABLE tds_data ADD COLUMN water_temp FLOAT"))
            db.session.execute(text("ALTER TABLE tds_data ADD COLUMN air_temp FLOAT"))
            db.session.commit()
            print("DEBUG MIGRATION: tds_data migrated successfully.")
        except Exception as e:
            db.session.rollback()
            print(f"DEBUG MIGRATION: tds_data migration failed: {e}")

    try:
        db.session.execute(text("SELECT water_temp, air_temp FROM ph_data LIMIT 1"))
        print("DEBUG MIGRATION: ph_data already contains temperature columns.")
    except Exception:
        print("DEBUG MIGRATION: Migrating ph_data table...")
        db.session.rollback()
        try:
            db.session.execute(text("ALTER TABLE ph_data ADD COLUMN water_temp FLOAT"))
            db.session.execute(text("ALTER TABLE ph_data ADD COLUMN air_temp FLOAT"))
            db.session.commit()
            print("DEBUG MIGRATION: ph_data migrated successfully.")
        except Exception as e:
            db.session.rollback()
            print(f"DEBUG MIGRATION: ph_data migration failed: {e}")

@socketio.on('connect')
def handle_connect():
    print("DEBUG: Client Connected to SocketIO")
    global camera_task_started
    if 'camera_task_started' not in globals():
        socketio.start_background_task(camera_worker)
        globals()['camera_task_started'] = True

@socketio.on('disconnect')
def handle_disconnect():
    print("DEBUG: Client Disconnected from SocketIO")

if __name__ == "__main__":
    with app.app_context():
        db.create_all()
        run_migrations()
        if not PlantStageStatus.query.first(): db.session.add(PlantStageStatus(plant_name="", plant_stage="Vegetative", state=False))
        
        hal.initialize_hardware()
        
        # Seed initial default presets if the table is empty
        if PlantPreset.query.count() == 0:
            import json
            default_stages = json.dumps({
                "Vegetative": {"ec": {"min": 1.2, "max": 2.0}, "ph": {"min": 5.8, "max": 6.8}},
                "Flowering": {"ec": {"min": 1.8, "max": 2.5}, "ph": {"min": 6.0, "max": 6.5}},
                "Maturity": {"ec": {"min": 1.5, "max": 2.0}, "ph": {"min": 5.5, "max": 6.0}}
            })
            db.session.add(PlantPreset(name="Tomato", image_url="/images/tomato.jpg", stages_json=default_stages))
            db.session.add(PlantPreset(name="Spinach", image_url="/images/spinach.jpg", stages_json=default_stages))
            db.session.add(PlantPreset(name="Lettuce", image_url="/images/lettuce.jpg", stages_json=default_stages))
            db.session.add(PlantPreset(name="Strawberry", image_url="/images/strawberry.PNG", stages_json=default_stages))
        
        # Seed default sensor limits if empty
        if SensorLimits.query.count() == 0:
            db.session.add(SensorLimits(sensor_type='ph', min_value=5.5, max_value=7.0, is_active=False))
            db.session.add(SensorLimits(sensor_type='tds', min_value=1.0, max_value=3.0, is_active=False))
            db.session.add(SensorLimits(sensor_type='temperature', min_value=18, max_value=30, is_active=False))
            db.session.add(SensorLimits(sensor_type='humidity', min_value=40, max_value=80, is_active=False))
        
        db.session.commit()
        log_event("SYSTEM_STARTUP", "SYSTEM", "Controller service initialized successfully.")
        
        # Start ML loop if active
        status_rec = PlantStageStatus.query.first()
        if status_rec and status_rec.state:
            start_plant_monitor()
            
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    socketio.start_background_task(fetch_loop)
    socketio.start_background_task(aggregation_loop)
    socketio.start_background_task(daily_digest_loop)
    socketio.run(app, host='0.0.0.0', port=5000, debug=True, use_reloader=False, allow_unsafe_werkzeug=True)
