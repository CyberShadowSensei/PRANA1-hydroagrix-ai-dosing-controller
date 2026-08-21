print("HELLO! THE BACKEND IS STARTING (GOLDEN SYNC FINAL)!")
import sys
import os
import time
import threading
import signal
from datetime import datetime, timedelta
import pytz

from config import app, db, socketio
from models import PlantStageStatus, PlantPreset, SensorLimits, PHData, TDSData, TemperatureHumidityData, SolutionTanks
import hal

from routes import *
from sensors import fetch_ph, fetch_tds, fetch_th, log_event, live_ph_data, live_tds_data, live_th_data
from dosing import check_and_adjust_sensors
from camera_ml import camera_worker, generate_timelapse, start_plant_monitor

def signal_handler(sig, frame):
    print("DEBUG: Shutting down backend...")
    log_event("SYSTEM_SHUTDOWN", "SYSTEM", "Controller service shutdown requested.")
    try:
        with app.app_context():
            from sqlalchemy import text
            db.session.execute(text('PRAGMA wal_checkpoint(FULL);'))
    except Exception as e:
        print(f"WAL Checkpoint warning: {e}")
    hal.cleanup()
    sys.exit(0)

# --- BACKGROUND THREADS ---

_last_mail_check = 0.0

_last_telemetry_emitted = None
_fetch_tick_count = 0

def fetch_loop():
    global _last_mail_check, _last_telemetry_emitted, _fetch_tick_count
    while True:
        try:
            with app.test_request_context():
                from sensors import get_water_temp
                w_t, is_est = get_water_temp()
                ph_res = fetch_ph(w_t)
                tds_res = fetch_tds(w_t)
                
                # DHT22 sensor is cached at 2.0s in HAL, so poll every 4th tick (2.0s)
                if _fetch_tick_count % 4 == 0 or not live_th_data:
                    th_res = fetch_th()
                else:
                    latest_th = live_th_data[-1] if live_th_data else {}
                    th_res = {
                        'temperature': latest_th.get('t', 25.0),
                        'humidity': latest_th.get('h', 0.0),
                        'status': latest_th.get('status', 'ERROR')
                    }
                _fetch_tick_count += 1
                
                current_telemetry = {
                    'ph': ph_res.get('ph_value'),
                    'ec': tds_res.get('tds_value'),
                    'temperature': th_res.get('temperature'),
                    'humidity': th_res.get('humidity'),
                    'pumps': {f"pump{k}": v for k, v in hal.pump_status.items()}
                }
                
                # Emit only if telemetry changed or 5 seconds elapsed (heartbeat)
                now_t = time.time()
                should_emit = False
                if _last_telemetry_emitted is None or (now_t - _last_telemetry_emitted.get('_time', 0)) >= 5.0:
                    should_emit = True
                else:
                    # Compare values against last emitted
                    last = _last_telemetry_emitted
                    if (current_telemetry['pumps'] != last['pumps'] or
                        current_telemetry['ph'] != last['ph'] or
                        current_telemetry['ec'] != last['ec'] or
                        current_telemetry['temperature'] != last['temperature'] or
                        current_telemetry['humidity'] != last['humidity']):
                        should_emit = True
                
                if should_emit:
                    socketio.emit('telemetry_update', current_telemetry)
                    current_telemetry['_time'] = now_t
                    _last_telemetry_emitted = current_telemetry
                
                check_and_adjust_sensors()

                # Throttle sensor mail check to once per 60 seconds.
                if now_t - _last_mail_check >= 60.0:
                    process_status_mail_check()
                    _last_mail_check = now_t
        except Exception as e:
            import traceback
            print(f"CRITICAL ERROR in fetch_loop: {e}")
            traceback.print_exc()
        time.sleep(0.5)




def aggregation_loop():
    while True:
        time.sleep(600)
        try:
            with app.app_context():
                if live_ph_data:
                    n = len(live_ph_data)
                    tot_ph, tot_w, tot_a = 0.0, 0.0, 0.0
                    for d in live_ph_data:
                        tot_ph += d["value"]
                        tot_w += d.get("water_temp", 25.0)
                        tot_a += d.get("air_temp", 25.0)
                    db.session.add(PHData(
                        ph_value=round(tot_ph / n, 2),
                        water_temp=round(tot_w / n, 2),
                        air_temp=round(tot_a / n, 2)
                    ))
                if live_tds_data:
                    n = len(live_tds_data)
                    tot_tds, tot_w, tot_a = 0.0, 0.0, 0.0
                    for d in live_tds_data:
                        tot_tds += d["value"]
                        tot_w += d.get("water_temp", 25.0)
                        tot_a += d.get("air_temp", 25.0)
                    db.session.add(TDSData(
                        tds_value=round(tot_tds / n, 2),
                        water_temp=round(tot_w / n, 2),
                        air_temp=round(tot_a / n, 2)
                    ))
                if live_th_data:
                    n = len(live_th_data)
                    tot_t, tot_h = 0.0, 0.0
                    for d in live_th_data:
                        tot_t += d["t"]
                        tot_h += d["h"]
                    db.session.add(TemperatureHumidityData(
                        temperature=round(tot_t / n, 2),
                        humidity=round(tot_h / n, 2)
                    ))
                db.session.commit()
                print("DEBUG: 10-Minute Data Aggregation Committed to DB.")
        except Exception as e:
            print(f"DEBUG: aggregation_loop failed: {e}")



def process_email_backlog_items():
    """Processes pending email backlog items, handling connectivity vs recipient/message errors."""
    with app.app_context():
        from models import EmailBacklog
        from checkSensorMail import SensorMonitor
        from email.mime.text import MIMEText
        from email.mime.multipart import MIMEMultipart
        from email.utils import formatdate, make_msgid
        import smtplib

        # Discard older than 24 hours
        cutoff = datetime.utcnow() - timedelta(hours=24)
        EmailBacklog.query.filter(EmailBacklog.created_at < cutoff).delete(synchronize_session=False)
        db.session.commit()

        # Fetch pending emails
        pending_emails = EmailBacklog.query.order_by(EmailBacklog.created_at.asc()).all()
        if pending_emails:
            # Reuse the existing sensor_monitor singleton from sensors.py instead of
            # constructing a new SensorMonitor() — which reads email_config.json from
            # disk on every invocation (every 60 seconds).
            from sensors import sensor_monitor as _monitor
            email_config = _monitor.email_config
            
            if email_config.get('sender_email') != 'placeholder@gmail.com':
                for backlog_item in pending_emails:
                    try:
                        msg = MIMEMultipart('mixed')
                        msg['From'] = email_config['sender_email']
                        msg['Date'] = formatdate(localtime=True)
                        msg['Message-ID'] = make_msgid()
                        recipients = [r.strip() for r in backlog_item.recipients.split(',') if r.strip()]
                        msg['To'] = ", ".join(recipients)
                        from email.header import Header
                        msg['Subject'] = Header(backlog_item.subject, 'utf-8')

                        delay_note = f"\n\n[NOTE: This is a delayed message originally generated at {backlog_item.created_at.strftime('%Y-%m-%d %H:%M:%S UTC')}]"
                        plain_text = backlog_item.body_text + delay_note
                        
                        alt_part = MIMEMultipart('alternative')
                        alt_part.attach(MIMEText(plain_text, 'plain'))
                        
                        if backlog_item.body_html:
                            html_delay_note = f"<br><br><div style='color: #fbbf24; font-size: 12px;'>[NOTE: This is a delayed message originally generated at {backlog_item.created_at.strftime('%Y-%m-%d %H:%M:%S UTC')}]</div>"
                            html_body = backlog_item.body_html
                            if '</body>' in html_body:
                                html_body = html_body.replace('</body>', html_delay_note + '</body>')
                            else:
                                html_body += html_delay_note
                            alt_part.attach(MIMEText(html_body, 'html'))
                        
                        msg.attach(alt_part)
                        
                        with smtplib.SMTP(email_config.get('smtp_server'), email_config.get('smtp_port'), timeout=15) as server:
                            server.starttls()
                            server.login(email_config.get('sender_email'), email_config.get('sender_password'))
                            server.send_message(msg, to_addrs=recipients)
                        
                        # Send successful, delete from backlog
                        db.session.delete(backlog_item)
                        db.session.commit()
                    except (smtplib.SMTPConnectError, smtplib.SMTPServerDisconnected, TimeoutError, OSError) as e:
                        print(f"Network/Connection error sending backlogged email {backlog_item.id}: {e}")
                        # Connection or server connectivity failure - break loop to retry entire queue later
                        break
                    except Exception as e:
                        print(f"Recipient or message error sending backlogged email {backlog_item.id}: {e}. Removing item from queue.")
                        # Bad recipient / invalid message format / 5xx error - log, delete item, and continue queue
                        db.session.delete(backlog_item)
                        db.session.commit()

def email_backlog_loop():
    while True:
        try:
            process_email_backlog_items()
        except Exception as e:
            print(f"Error in email_backlog_loop: {e}")
        
        time.sleep(60)

def prune_old_photos(photo_dir="captured_photos", max_days=30):
    """Deletes photo files in photo_dir with a modification time older than max_days."""
    if not os.path.exists(photo_dir):
        return
    now = time.time()
    cutoff = now - (max_days * 86400)
    for filename in os.listdir(photo_dir):
        filepath = os.path.join(photo_dir, filename)
        if os.path.isfile(filepath):
            try:
                if os.path.getmtime(filepath) < cutoff:
                    os.remove(filepath)
                    print(f"DEBUG: Pruned old photo artifact: {filepath}")
            except Exception as e:
                print(f"DEBUG: Failed to prune photo {filepath}: {e}")

def _seconds_until_ist(target_hour, target_minute=0):
    """Return seconds until the next occurrence of target_hour:target_minute IST."""
    from sensors import IST
    now = datetime.now(IST)
    target = now.replace(hour=target_hour, minute=target_minute, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return max(60.0, (target - now).total_seconds())


def daily_digest_loop():
    while True:
        try:
            from sensors import IST
            now = datetime.now(IST)

            if now.hour == 2 and now.minute == 0:

                print("DEBUG: Auto-generating time-lapse at 2:00 AM")
                generate_timelapse()
                
                with app.app_context():
                    from models import EventLog, PumpLog
                    threshold_date = datetime.utcnow() - timedelta(days=30)
                    try:
                        PHData.query.filter(PHData.timestamp < threshold_date).delete(synchronize_session=False)
                        TDSData.query.filter(TDSData.date < threshold_date).delete(synchronize_session=False)
                        TemperatureHumidityData.query.filter(TemperatureHumidityData.date < threshold_date).delete(synchronize_session=False)
                        EventLog.query.filter(EventLog.timestamp < threshold_date).delete(synchronize_session=False)
                        PumpLog.query.filter(PumpLog.timestamp < threshold_date).delete(synchronize_session=False)
                        db.session.commit()
                        print("DEBUG: Pruned telemetry and logs older than 30 days.")
                    except Exception as e:
                        db.session.rollback()
                        print(f"DEBUG: Pruning failed: {e}")
                
                prune_old_photos(photo_dir="captured_photos", max_days=30)
                # Sleep 65s so we don't re-trigger within the same minute
                time.sleep(65)
                continue

            if now.hour == 8 and now.minute == 0:
                print("DEBUG: Sending Daily Digest at 8:00 AM")
                is_weekly = (now.weekday() == 6)  # Sunday
                with app.test_client() as client:
                    client.post('/send_report_email', json={"include_ml_analysis": is_weekly})
                time.sleep(65)
                continue

        except Exception as e:
            print(f"Daily digest error: {e}")

        # Sleep precisely until whichever target comes next.
        # This replaces the 30-second busy-poll (2,880 wake-ups/day -> ~2).
        secs_to_2am = _seconds_until_ist(2, 0)
        secs_to_8am = _seconds_until_ist(8, 0)
        sleep_secs = min(secs_to_2am, secs_to_8am)
        time.sleep(sleep_secs)



def run_migrations():
    from sqlalchemy import text, inspect
    try:
        inspector = inspect(db.engine)
        
        for table in ['ph_data', 'tds_data', 'temperature_humidity_data', 'pump_log', 'event_log']:
            if table in inspector.get_table_names():
                col_name = 'date' if table in ['tds_data', 'temperature_humidity_data'] else 'timestamp'
                try:
                    db.session.execute(text(f"CREATE INDEX IF NOT EXISTS idx_{table}_date ON {table}({col_name})"))
                    db.session.commit()
                except Exception as e:
                    db.session.rollback()
                    print(f"DEBUG MIGRATION: Index creation failed for {table}: {e}")
    except Exception as e:
        print(f"DEBUG MIGRATION: Could not inspect DB: {e}")
        return

    if 'tds_data' in inspector.get_table_names():
        columns = [c['name'] for c in inspector.get_columns('tds_data')]
        if 'water_temp' not in columns:
            print("DEBUG MIGRATION: Migrating tds_data table...")
            try:
                db.session.execute(text("ALTER TABLE tds_data ADD COLUMN water_temp FLOAT"))
                db.session.execute(text("ALTER TABLE tds_data ADD COLUMN air_temp FLOAT"))
                db.session.commit()
            except Exception as e:
                db.session.rollback()
                print(f"DEBUG MIGRATION: tds_data migration failed: {e}")

    if 'ph_data' in inspector.get_table_names():
        columns = [c['name'] for c in inspector.get_columns('ph_data')]
        if 'water_temp' not in columns:
            print("DEBUG MIGRATION: Migrating ph_data table...")
            try:
                db.session.execute(text("ALTER TABLE ph_data ADD COLUMN water_temp FLOAT"))
                db.session.execute(text("ALTER TABLE ph_data ADD COLUMN air_temp FLOAT"))
                db.session.commit()
            except Exception as e:
                db.session.rollback()
                print(f"DEBUG MIGRATION: ph_data migration failed: {e}")

    if 'plant_stage_status' in inspector.get_table_names():
        columns = [c['name'] for c in inspector.get_columns('plant_stage_status')]
        if 'cycle_start_date' not in columns:
            print("DEBUG MIGRATION: Migrating plant_stage_status table...")
            try:
                db.session.execute(text("ALTER TABLE plant_stage_status ADD COLUMN cycle_start_date DATETIME"))
                db.session.commit()
            except Exception as e:
                db.session.rollback()
                print(f"DEBUG MIGRATION: plant_stage_status migration failed: {e}")

    for table in ['ph_data', 'tds_data', 'temperature_humidity_data', 'pump_log', 'event_log']:
        if table in inspector.get_table_names():
            columns = [c['name'] for c in inspector.get_columns(table)]
            if 'archived' not in columns:
                print(f"DEBUG MIGRATION: Migrating {table} table to add archived column...")
                try:
                    db.session.execute(text(f"ALTER TABLE {table} ADD COLUMN archived BOOLEAN DEFAULT 0"))
                    db.session.commit()
                except Exception as e:
                    db.session.rollback()
                    print(f"DEBUG MIGRATION: {table} migration failed: {e}")

    if 'plant_preset' in inspector.get_table_names():
        columns = [c['name'] for c in inspector.get_columns('plant_preset')]
        if 'is_continuous_harvest' not in columns:
            print("DEBUG MIGRATION: Migrating plant_preset table...")
            try:
                db.session.execute(text("ALTER TABLE plant_preset ADD COLUMN is_continuous_harvest BOOLEAN DEFAULT 0"))
                db.session.execute(text("ALTER TABLE plant_preset ADD COLUMN is_builtin BOOLEAN DEFAULT 0"))
                db.session.execute(text("ALTER TABLE plant_preset ADD COLUMN is_hidden BOOLEAN DEFAULT 0"))
                db.session.commit()
            except Exception as e:
                db.session.rollback()
                print(f"DEBUG MIGRATION: plant_preset migration failed: {e}")

    if 'solution_tanks' in inspector.get_table_names():
        columns = [c['name'] for c in inspector.get_columns('solution_tanks')]
        if 'consecutive_blocked_attempts' not in columns:
            print("DEBUG MIGRATION: Migrating solution_tanks table...")
            try:
                db.session.execute(text("ALTER TABLE solution_tanks ADD COLUMN consecutive_blocked_attempts INTEGER DEFAULT 0"))
                db.session.execute(text("ALTER TABLE solution_tanks ADD COLUMN next_allowed_alert_time FLOAT DEFAULT 0.0"))
                db.session.commit()
            except Exception as e:
                db.session.rollback()
                print(f"DEBUG MIGRATION: solution_tanks migration failed: {e}")

@socketio.on('connect')
def handle_connect():
    print("DEBUG: Client Connected to SocketIO")

@socketio.on('disconnect')
def handle_disconnect():
    print("DEBUG: Client Disconnected from SocketIO")

if __name__ == "__main__":
    with app.app_context():
        db.create_all()
        run_migrations()
        if not PlantStageStatus.query.first(): db.session.add(PlantStageStatus(plant_name="", plant_stage="Vegetative", state=False))
        
        hal.initialize_hardware()
        from dosing import check_tank_has_solution_permission
        hal.pump_permission_check = check_tank_has_solution_permission

        if SolutionTanks.query.count() == 0:
            db.session.add(SolutionTanks(tank_id=1, name="Nutrient A", capacity_ml=5000.0, current_volume_ml=5000.0))
            db.session.add(SolutionTanks(tank_id=2, name="Nutrient B", capacity_ml=5000.0, current_volume_ml=5000.0))
            db.session.add(SolutionTanks(tank_id=3, name="pH UP", capacity_ml=5000.0, current_volume_ml=5000.0))
            db.session.add(SolutionTanks(tank_id=4, name="pH DOWN", capacity_ml=5000.0, current_volume_ml=5000.0))
            db.session.commit()
        
        # Seed initial default presets if the table is empty
        import json
        tomato_stages = json.dumps({
            "Seedling": {"duration_days": 21, "buffer_days": 3, "start_day": 0, "ec": {"min": 1.0, "max": 1.5}, "ph": {"min": 5.5, "max": 6.5}},
            "Vegetative": {"duration_days": 25, "buffer_days": 4, "start_day": 24, "ec": {"min": 1.5, "max": 2.5}, "ph": {"min": 5.5, "max": 6.5}},
            "Maturity": {"duration_days": 56, "buffer_days": 0, "start_day": 53, "ec": {"min": 2.5, "max": 3.5}, "ph": {"min": 5.5, "max": 6.5}}
        })
        lettuce_stages = json.dumps({
            "Seedling": {"duration_days": 14, "buffer_days": 2, "start_day": 0, "ec": {"min": 0.6, "max": 1.0}, "ph": {"min": 5.5, "max": 6.0}},
            "Vegetative": {"duration_days": 19, "buffer_days": 3, "start_day": 16, "ec": {"min": 1.0, "max": 1.4}, "ph": {"min": 5.5, "max": 6.0}},
            "Maturity": {"duration_days": 7, "buffer_days": 0, "start_day": 38, "ec": {"min": 1.2, "max": 1.6}, "ph": {"min": 5.5, "max": 6.0}}
        })
        basil_stages = json.dumps({
            "Seedling": {"duration_days": 14, "buffer_days": 2, "start_day": 0, "ec": {"min": 0.8, "max": 1.2}, "ph": {"min": 5.5, "max": 6.5}},
            "Vegetative": {"duration_days": 19, "buffer_days": 3, "start_day": 16, "ec": {"min": 1.2, "max": 1.6}, "ph": {"min": 5.5, "max": 6.5}},
            "Maturity": {"duration_days": 27, "buffer_days": 0, "start_day": 38, "ec": {"min": 1.6, "max": 2.0}, "ph": {"min": 5.5, "max": 6.5}}
        })
        spinach_stages = json.dumps({
            "Seedling": {"duration_days": 14, "buffer_days": 2, "start_day": 0, "ec": {"min": 0.8, "max": 1.2}, "ph": {"min": 6.0, "max": 7.0}},
            "Vegetative": {"duration_days": 19, "buffer_days": 3, "start_day": 16, "ec": {"min": 1.2, "max": 1.6}, "ph": {"min": 6.0, "max": 7.0}},
            "Maturity": {"duration_days": 12, "buffer_days": 0, "start_day": 38, "ec": {"min": 1.6, "max": 2.0}, "ph": {"min": 6.0, "max": 7.0}}
        })
        strawberry_stages = json.dumps({
            "Seedling": {"duration_days": 21, "buffer_days": 3, "start_day": 0, "ec": {"min": 0.8, "max": 1.0}, "ph": {"min": 5.5, "max": 6.2}},
            "Vegetative": {"duration_days": 25, "buffer_days": 4, "start_day": 24, "ec": {"min": 1.0, "max": 1.2}, "ph": {"min": 5.5, "max": 6.2}},
            "Maturity": {"duration_days": 38, "buffer_days": 0, "start_day": 53, "ec": {"min": 1.2, "max": 1.5}, "ph": {"min": 5.5, "max": 6.2}}
        })
        tulsi_basil_stages = json.dumps({
            "Seedling": {"duration_days": 14, "buffer_days": 2, "start_day": 0, "ec": {"min": 0.8, "max": 1.2}, "ph": {"min": 5.8, "max": 6.5}},
            "Vegetative": {"duration_days": 19, "buffer_days": 3, "start_day": 16, "ec": {"min": 1.2, "max": 1.5}, "ph": {"min": 5.8, "max": 6.5}},
            "Maturity": {"duration_days": 22, "buffer_days": 0, "start_day": 38, "ec": {"min": 1.4, "max": 1.8}, "ph": {"min": 5.8, "max": 6.5}}
        })
        
        default_data = {
            "Tomatoes": {"image_url": "/images/tomato.jpg", "stages": tomato_stages, "continuous": True},
            "Lettuce": {"image_url": "/images/lettuce.jpg", "stages": lettuce_stages, "continuous": False},
            "Basil": {"image_url": "/images/basil.jpg", "stages": basil_stages, "continuous": True},
            "Spinach": {"image_url": "/images/spinach.jpg", "stages": spinach_stages, "continuous": False},
            "Strawberry": {"image_url": "/images/strawberry.PNG", "stages": strawberry_stages, "continuous": True},
            "Tulsi/Basil": {"image_url": "/images/tulsi_basil.jpg", "stages": tulsi_basil_stages, "continuous": True}
        }
        
        # Find all existing presets in the database
        existing_presets = {p.name: p for p in PlantPreset.query.all()}
        
        # Upsert: Insert if missing, otherwise update existing built-in presets
        for name, data in default_data.items():
            if name not in existing_presets:
                # Insert the missing preset (e.g., Tulsi/Basil)
                db.session.add(PlantPreset(
                    name=name,
                    image_url=data["image_url"],
                    stages_json=data["stages"],
                    is_continuous_harvest=data["continuous"],
                    is_builtin=True,
                    is_hidden=False
                ))
            else:
                # Update existing preset
                preset = existing_presets[name]
                preset.stages_json = data["stages"]
                preset.is_continuous_harvest = data["continuous"]
                preset.is_builtin = True
                # Preserve is_hidden status so user-deleted presets remain hidden/deleted
                db.session.add(preset)
                
        # We also need to process any custom presets to ensure they use "Maturity" instead of "Harvesting"
        for preset in existing_presets.values():
            if preset.name not in default_data and preset.stages_json:
                try:
                    stages = json.loads(preset.stages_json)
                    if "Harvesting" in stages:
                        stages["Maturity"] = stages.pop("Harvesting")
                        preset.stages_json = json.dumps(stages)
                        db.session.add(preset)
                except Exception:
                    pass
        
        # Seed default sensor limits if empty
        if SensorLimits.query.count() == 0:
            db.session.add(SensorLimits(sensor_type='ph', min_value=5.5, max_value=7.0, is_active=False))
            db.session.add(SensorLimits(sensor_type='tds', min_value=1.0, max_value=3.0, is_active=False))
            db.session.add(SensorLimits(sensor_type='temperature', min_value=18, max_value=30, is_active=False))
            db.session.add(SensorLimits(sensor_type='humidity', min_value=40, max_value=80, is_active=False))
            
        if PlantStageStatus.query.count() == 0:
            db.session.add(PlantStageStatus(plant_name="", plant_stage="Idle", state=False))
        db.session.commit()
        import db_cache
        db_cache.init_cache(app, db)
        log_event("SYSTEM_STARTUP", "SYSTEM", "Controller service initialized successfully.")
        
        # Start ML loop if active
        status_rec = PlantStageStatus.query.first()
        if status_rec and status_rec.state:
            start_plant_monitor()
            
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    socketio.start_background_task(camera_worker)
    socketio.start_background_task(email_backlog_loop)
    socketio.start_background_task(fetch_loop)
    socketio.start_background_task(aggregation_loop)
    socketio.start_background_task(daily_digest_loop)
    socketio.run(app, host='0.0.0.0', port=5000, debug=True, use_reloader=False, allow_unsafe_werkzeug=True)
