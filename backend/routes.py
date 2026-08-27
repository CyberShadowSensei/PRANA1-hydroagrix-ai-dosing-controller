import os
import time
import json
import threading
import io
from io import BytesIO
import pytz
from datetime import datetime, timedelta
import requests
import csv
import glob
import html

from flask import request, jsonify, send_file, send_from_directory, abort, current_app
from config import app, db, socketio
import hal
from models import MoistureSensorData, TemperatureHumidityData, PhotoRecord, TDSData, PHData, SensorLimits, PlantStageStatus, PumpLog, PlantPreset, PresetAuditLog, EventLog, SolutionTanks, EmailAuditLog
from reporting import generate_cycle_reports
import grow_cycle_helper

from sensors import live_ph_data, live_tds_data, live_th_data, fetch_ph, fetch_tds, fetch_th, sensor_monitor, log_event
import dosing
from dosing import log_pump_action, check_and_adjust_sensors
from camera_ml import PHOTO_DIRECTORY, set_stream_running, start_plant_monitor, generate_timelapse

# --- FLASK ROUTES ---

@app.route("/get_location")
@app.route("/get-location")
def get_loc():
    try:
        ip = requests.get("https://api64.ipify.org?format=json", timeout=3).json()["ip"]
        return jsonify(requests.get(f"http://ip-api.com/json/{ip}", timeout=3).json()), 200
    except Exception: return jsonify({"city": "Local", "lat": 0, "lon": 0, "isp": "Offline"}), 200

@app.route("/get_plant_status")
def g_plant_status():
    s = PlantStageStatus.query.first()
    if not s:
        s = PlantStageStatus(plant_name="", plant_stage="Idle", state=False)
        db.session.add(s)
        db.session.commit()
    return jsonify(s.to_json()), 200

@app.route("/update_plant_status", methods=["POST"])
def u_plant_status():
    s = PlantStageStatus.query.first()
    if not s:
        s = PlantStageStatus(plant_name="", plant_stage="Idle", state=False)
        db.session.add(s)
    if 'state' in request.json: 
        if not s.plant_name:
            return jsonify({"error": "A growth cycle must be active to configure system mode."}), 400
        s.state = request.json['state']
        mode_str = "AUTONOMOUS" if s.state else "MANUAL"
        log_event("CONTROL_MODE_CHANGED", "INFO", f"System control mode set to: {mode_str}")
        print(f"INFO SYSTEM_MODE: Control mode set to {mode_str}")
        if s.state: start_plant_monitor()
    db.session.commit()
    socketio.emit('grow_cycle_update', grow_cycle_helper.get_active_grow_cycle_details())
    return jsonify(s.to_json()), 200

@app.route("/set_active_plant", methods=["POST"])
def s_active_plant():
    from reporting import generate_cycle_report
    from datetime import datetime
    s = PlantStageStatus.query.first()
    if not s:
        s = PlantStageStatus(plant_name="", plant_stage="Idle", state=False)
        db.session.add(s)
        
    if 'plant_name' in request.json:
        new_plant = request.json['plant_name']
        if s.plant_name and s.plant_name != new_plant:
            if s.cycle_start_date:
                threading.Thread(target=generate_cycle_report, args=("Interrupted",), daemon=True).start()
        s.plant_name = new_plant
        s.cycle_start_date = datetime.utcnow()
        preset = PlantPreset.query.filter_by(name=new_plant).first()
        if preset:
            try:
                stages = json.loads(preset.stages_json)
                sorted_stages = sorted(stages.items(), key=lambda x: x[1].get('start_day', 0))
                if sorted_stages:
                    s.plant_stage = sorted_stages[0][0]
            except: pass
    db.session.commit()
    socketio.emit('grow_cycle_update', grow_cycle_helper.get_active_grow_cycle_details())
    try:
        from camera_ml import detect_plant_stage
        threading.Thread(target=detect_plant_stage, daemon=True).start()
    except Exception as e:
        print(f"Error triggering ML analysis: {e}")
    return jsonify(s.to_json()), 200

@app.route("/complete_cycle", methods=["POST"])
def complete_cycle():
    from reporting import generate_cycle_report
    s = PlantStageStatus.query.first()
    if s and s.plant_name:
        threading.Thread(target=generate_cycle_report, args=("Completed",), daemon=True).start()
        log_event("CYCLE_COMPLETED", "SYSTEM", f"Grow cycle for {s.plant_name} completed.")
        s.plant_name = ""
        s.plant_stage = "Idle"
        db.session.commit()
        socketio.emit('grow_cycle_update', grow_cycle_helper.get_active_grow_cycle_details())
        return jsonify({"message": "Cycle completed successfully."}), 200
    return jsonify({"error": "No active cycle to complete."}), 400

@app.route("/get_ph")
def get_ph():
    if live_ph_data:
        last = live_ph_data[-1]
        return jsonify({"ph_value": last["value"], "status": last["status"]})
    return jsonify(fetch_ph())

@app.route("/get_tds")
def get_tds():
    if live_tds_data:
        last = live_tds_data[-1]
        return jsonify({"tds_value": last["value"], "status": last["status"]})
    return jsonify(fetch_tds())

@app.route("/get_temperature_humidity")
def get_th():
    if live_th_data:
        last = live_th_data[-1]
        return jsonify({"temperature": last["t"], "humidity": last["h"], "status": last["status"]})
    return jsonify(fetch_th())

@app.route("/api/live_gauges")
def live_gauges():
    ph = live_ph_data[-1] if live_ph_data else {"value": None, "status": "No Data"}
    tds = live_tds_data[-1] if live_tds_data else {"value": None, "status": "No Data"}
    th = live_th_data[-1] if live_th_data else {"t": None, "h": None, "status": "No Data"}
    return jsonify({
        "ph": {"value": ph.get("value"), "status": ph.get("status")},
        "tds": {"value": tds.get("value"), "status": tds.get("status")},
        "temperature": {"value": th.get("t"), "status": th.get("status")},
        "humidity": {"value": th.get("h"), "status": th.get("status")}
    })

@app.route("/sensor_status")
def sensor_status():
    # Deprecated for UI, but kept for backwards compatibility
    return live_gauges()

manual_pump_starts = {}

def auto_stop_pump_monitored(pump_id, duration):
    print(f"DEBUG ROUTES: auto_stop thread started for pump={pump_id}, duration={duration}")
    time.sleep(duration)
    print(f"DEBUG ROUTES: auto_stop thread woke up for pump={pump_id}")
    with hal.pump_lock:
        if hal.pump_status.get(pump_id) == "running":
            hal.pump_stop(pump_id)
            print(f"DEBUG ROUTES: auto_stop thread stopped pump={pump_id}, hal.pump_status = {hal.pump_status}")
            record = manual_pump_starts.get(pump_id)
            if record and not record.get("logged"):
                record["logged"] = True
                actual_duration = round(time.time() - record["start_time"], 1)
                actual_duration = min(actual_duration, duration)
                log_pump_action(pump_id, actual_duration, record["trigger_type"])

@app.route("/pump/status")
def p_status():
    status_dict = {f"pump{k}": v for k, v in hal.pump_status.items()}
    print(f"DEBUG ROUTES: /pump/status response = {status_dict}")
    return jsonify(status_dict)

@app.route("/pump/<int:pump_id>/start", methods=["POST"])
def start_p(pump_id):
    data = request.get_json(silent=True) or {}
    d = data.get("duration", 5)
    print(f"DEBUG ROUTES: /pump/{pump_id}/start hit with duration={d}")
    if pump_id in hal.PUMP_PINS:
        with hal.pump_lock:
            hal.pump_start(pump_id)
            print(f"DEBUG ROUTES: After pump_start, hal.pump_status = {hal.pump_status}")
            manual_pump_starts[pump_id] = {
                "start_time": time.time(),
                "duration": d,
                "trigger_type": "Manual",
                "logged": False
            }
            threading.Thread(target=auto_stop_pump_monitored, args=(pump_id, d), daemon=True).start()
    return jsonify({"message": "OK"}), 200

@app.route("/pump/<int:pump_id>/stop", methods=["POST"])
def stop_p(pump_id):
    print(f"DEBUG ROUTES: /pump/{pump_id}/stop hit")
    dosing.request_dosing_cancellation()
    if pump_id in hal.PUMP_PINS:
        with hal.pump_lock:
            if hal.pump_status.get(pump_id) == "running":
                hal.pump_stop(pump_id)
                print(f"DEBUG ROUTES: After pump_stop, hal.pump_status = {hal.pump_status}")
                record = manual_pump_starts.get(pump_id)
                if record and not record.get("logged"):
                    record["logged"] = True
                    actual_duration = round(time.time() - record["start_time"], 1)
                    log_pump_action(pump_id, actual_duration, "Manual (Stopped Early)")
    return jsonify({"message": "Stopped"}), 200

@app.route("/pump/all/start", methods=["POST"])
def start_all_pumps_route():
    try:
        data = request.get_json() or {}; duration = data.get("duration", 5)
        with hal.pump_lock:
            for pump_id in hal.PUMP_PINS:
                hal.pump_start(pump_id)
                manual_pump_starts[pump_id] = {
                    "start_time": time.time(),
                    "duration": duration,
                    "trigger_type": "Manual (All)",
                    "logged": False
                }
                threading.Thread(target=auto_stop_pump_monitored, args=(pump_id, duration), daemon=True).start()
        return jsonify({"message": "All pumps started", "status": "running", "auto_stop": duration}), 200
    except Exception as e: return jsonify({"message": str(e)}), 400

def _prime_pumps_thread():
    try:
        for pump_id in [1, 2]:
            hal.pump_start(pump_id)
        time.sleep(5)
    finally:
        for pump_id in [1, 2]:
            hal.pump_stop(pump_id)
        dosing.is_priming_active = False

@app.route("/api/pumps/prime", methods=["POST"])
def prime_pumps():
    if dosing.is_priming_active:
        return jsonify({"error": "Priming is already active"}), 400
    
    dosing.is_priming_active = True
    threading.Thread(target=_prime_pumps_thread, daemon=True).start()
    return jsonify({"message": "Priming started"}), 200

@app.route("/pump/all/stop", methods=["POST"])
def stop_all_pumps_route():
    try:
        dosing.request_dosing_cancellation()
        with hal.pump_lock:
            for pump_id in hal.PUMP_PINS:
                if hal.pump_status.get(pump_id) == "running":
                    hal.pump_stop(pump_id)
                    record = manual_pump_starts.get(pump_id)
                    if record and not record.get("logged"):
                        record["logged"] = True
                        actual_duration = round(time.time() - record["start_time"], 1)
                        log_pump_action(pump_id, actual_duration, "Manual (All Stopped Early)")
        return jsonify({"message": "All pumps stopped", "status": "stopped"}), 200
    except Exception as e: return jsonify({"message": str(e)}), 400

@app.route("/get_relay_status", methods=["GET"])
def get_relay_status():
    # Return mock status for Grow Light relay until fully integrated
    return jsonify({"status": "OFF"})

@app.route("/get_relay_status_fan", methods=["GET"])
def get_relay_status_fan():
    # Return mock status for Fan relay until fully integrated
    return jsonify({"status": "OFF"})

@app.route("/get_latest_photo", methods=["GET"])
@app.route("/get-latest-photo", methods=["GET"])
def get_latest_photo():
    try:
        photos = sorted(glob.glob(os.path.join("captured_photos", "*.jpg")))
        if not photos:
            return jsonify({"error": "No photos found"}), 404
        return send_file(photos[-1], mimetype='image/jpeg')
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/start_stream", methods=["POST"])
def start_stream_route():
    from camera_ml import set_stream_running
    set_stream_running(True)
    return jsonify({"message": "Stream started"}), 200

@app.route("/stop_stream", methods=["POST"])
def stop_stream_route():
    from camera_ml import set_stream_running
    set_stream_running(False)
    return jsonify({"message": "Stream stopped"}), 200

@app.route("/get_pump_logs", methods=["GET"])
def get_pump_logs():
    try:
        logs = PumpLog.query.order_by(PumpLog.id.desc()).limit(50).all()
        return jsonify({"pump_logs": [log.to_json() for log in logs]}), 200
    except Exception as e:
        return jsonify({"message": str(e)}), 400

@app.route("/get_event_logs", methods=["GET"])
def get_event_logs():
    try:
        limit = int(request.args.get("limit", 100))
        event_id = request.args.get("event_id")
        category = request.args.get("category")
        
        query = EventLog.query
        if event_id:
            query = query.filter_by(event_id=event_id)
        if category:
            query = query.filter_by(category=category)
            
        logs = query.order_by(EventLog.id.desc()).limit(limit).all()
        return jsonify({"event_logs": [log.to_json() for log in logs]}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@app.route("/api/email/audit_logs", methods=["GET"])
@app.route("/api/email/audit-logs", methods=["GET"])
def get_email_audit_logs():
    try:
        limit = int(request.args.get("limit", 200))
        logs = EmailAuditLog.query.order_by(EmailAuditLog.id.desc()).limit(limit).all()
        return jsonify([log.to_json() for log in logs]), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@app.route("/api/dosing_events", methods=["GET"])
def get_dosing_events():
    try:
        limit = int(request.args.get("limit", 50))
        # Fetch both automated PUMP_ACTIVATION events and manual PumpLogs to construct a unified history
        events = EventLog.query.filter(
            EventLog.event_id.in_(["PUMP_ACTIVATION", "PUMP_ACTION"])
        ).order_by(EventLog.id.desc()).limit(limit).all()
        # Fetch manual pump actions
        manual_pumps = PumpLog.query.filter(PumpLog.trigger_type.like("%Manual%")).order_by(PumpLog.id.desc()).limit(limit).all()
        
        combined = []
        for e in events:
            combined.append({
                "type": "Automatic",
                "action": "Automated Dosing" if e.event_id == "PUMP_ACTIVATION" else e.event_id.replace("PUMP_ACTIVATION_", "").replace("_", " "),
                "reason": e.message,
                "details": e.to_json()["details"],
                "timestamp": e.to_json()["timestamp"],
                "raw_date": e.timestamp
            })
            
        for m in manual_pumps:
            combined.append({
                "type": "Manual",
                "action": f"{m.pump_name} Actuated",
                "reason": "User manually triggered pump via Dashboard",
                "details": {"duration_sec": m.duration},
                "timestamp": m.to_json()["timestamp"],
                "raw_date": m.timestamp
            })
            
        # Sort combined by raw_date descending
        combined.sort(key=lambda x: x["raw_date"], reverse=True)
        # Remove raw_date before sending
        for item in combined:
            del item["raw_date"]
            
        return jsonify(combined[:limit]), 200
    except Exception as e:
        return jsonify({"message": str(e)}), 400

@app.route("/get_moisture_data", methods=["GET"])
def get_moisture_data_route():
    try: all_data = MoistureSensorData.query.all(); return jsonify({"moisture_data": [{"id": d.id, "moisture_level": d.moisture_level, "state": d.state, "date": d.date} for d in all_data]}), 200
    except Exception as e: return jsonify({"message": str(e)}), 400

@app.route("/sensor/limits", methods=["GET", "POST"])
def limits():
    if request.method == "GET":
        l = SensorLimits.query.all()
        result = {x.sensor_type: {"min": x.min_value, "max": x.max_value, "active": x.is_active} for x in l}
        status = PlantStageStatus.query.first()
        if status:
            result["active_plant"] = status.plant_name
            if status.state:
                result["auto_mode"] = True
                preset = PlantPreset.query.filter_by(name=status.plant_name).first()
                if preset and status.plant_stage:
                    try:
                        stage_limits = preset.get_stage_limits(status.plant_stage)
                        if stage_limits:
                            if 'ph' in stage_limits:
                                is_active = result.get('ph', {}).get('active', False)
                                result['ph'] = {"min": stage_limits['ph']['min'], "max": stage_limits['ph']['max'], "active": is_active}
                            if 'ec' in stage_limits:
                                is_active = result.get('tds', {}).get('active', False)
                                result['tds'] = {"min": stage_limits['ec']['min'], "max": stage_limits['ec']['max'], "active": is_active}
                    except Exception:
                        pass
            else:
                result["auto_mode"] = False
        else:
            result["auto_mode"] = False
        cycle = grow_cycle_helper.get_active_grow_cycle_details()
        result["autonomous_limits"] = cycle.get("limits", {}) if cycle and cycle.get("active") else {}
        return jsonify(result)
    data = request.json
    if not data or not isinstance(data, dict):
        return jsonify({"error": "Invalid request payload. Expected JSON dictionary."}), 400

    for k, v in data.items():
        if not isinstance(v, dict):
            continue
        limit = SensorLimits.query.filter_by(sensor_type=k).first()
        if not limit:
            limit = SensorLimits(sensor_type=k, min_value=0.0, max_value=14.0, is_active=True)
            db.session.add(limit)

        if 'min' in v and v['min'] is not None:
            try:
                limit.min_value = float(v['min'])
            except (ValueError, TypeError):
                pass
        if 'max' in v and v['max'] is not None:
            try:
                limit.max_value = float(v['max'])
            except (ValueError, TypeError):
                pass
        if 'active' in v and v['active'] is not None:
            limit.is_active = bool(v['active'])

    db.session.commit()

    updated = {x.sensor_type: {"min": x.min_value, "max": x.max_value, "active": x.is_active}
               for x in SensorLimits.query.all()}
    socketio.emit('sensor_limits_updated', updated)
    # Also emit 'limits_updated' so the Dashboard can react in real-time
    # without a 5-minute poll cycle.
    socketio.emit('limits_updated', updated)
    return jsonify({"message": "Saved", "limits": updated}), 200

def generate_pdf_report_bytes():
    from reportlab.lib import colors
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.pagesizes import letter
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    elements = []
    styles = getSampleStyleSheet()
    elements.append(Paragraph("IoT Hydroponic System Status Report", styles['Title']))
    ph = PHData.query.order_by(PHData.id.desc()).first()
    tds = TDSData.query.order_by(TDSData.id.desc()).first()
    th = TemperatureHumidityData.query.order_by(TemperatureHumidityData.id.desc()).first()
    
    ph_val = f"{round(ph.ph_value, 2) if ph else 'N/A'}"
    ph_w_temp = f"{round(ph.water_temp, 1) if (ph and ph.water_temp is not None) else 'N/A'} C"
    ph_a_temp = f"{round(ph.air_temp, 1) if (ph and ph.air_temp is not None) else 'N/A'} C"
    
    tds_val = f"{round(tds.tds_value, 2) if tds else 'N/A'} mS/cm"
    tds_w_temp = f"{round(tds.water_temp, 1) if (tds and tds.water_temp is not None) else 'N/A'} C"
    tds_a_temp = f"{round(tds.air_temp, 1) if (tds and tds.air_temp is not None) else 'N/A'} C"
    
    summary_data = [
        ["Sensor", "Value", "Water Temp", "Air Temp"],
        ["pH", ph_val, ph_w_temp, ph_a_temp],
        ["EC", tds_val, tds_w_temp, tds_a_temp],
        ["Climate Temp", f"{th.temperature if th else 'N/A'} C", "-", f"{th.temperature if th else 'N/A'} C"],
        ["Climate Hum", f"{th.humidity if th else 'N/A'} %", "-", "-"]
    ]
    
    t_summary = Table(summary_data, colWidths=[120, 100, 100, 100])
    t_summary.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey), ('GRID', (0, 0), (-1, -1), 1, colors.black)]))
    elements.append(t_summary)
    doc.build(elements)
    buffer.seek(0)
    return buffer.getvalue()

@app.route("/download_database_pdf")
def dl_pdf():
    try:
        pdf_bytes = generate_pdf_report_bytes()
        return send_file(BytesIO(pdf_bytes), as_attachment=True, download_name="Hydroponics_Report.pdf", mimetype="application/pdf")
    except Exception as e: return str(e), 500

@app.route("/download_database_csv")
def dl_csv():
    try:
        from reporting import generate_cycle_report
        def _run_report():
            with app.app_context():
                generate_cycle_report("Requested")
        threading.Thread(target=_run_report, daemon=True).start()
        return jsonify({"message": "CSV and PDF report will be emailed shortly."}), 200
    except Exception as e: return str(e), 400

@app.route("/check_and_adjust_sensors", methods=["GET", "POST"])
def ch_a(): check_and_adjust_sensors(); return jsonify({"message": "OK"}), 200

@app.route("/get_tank_levels", methods=["GET"])
def get_tank_levels():
    import db_cache
    tanks = db_cache.get_solution_tanks()
    return jsonify([
        {
            "tank_id": tid,
            "name": t["name"],
            "capacity_ml": t["capacity_ml"],
            "current_volume_ml": t["current_volume_ml"],
            "last_alert_sent": t["last_alert_sent"]
        }
        for tid, t in tanks.items()
    ]), 200

@app.route("/refill_tank", methods=["POST"])
def refill_tank():
    tank_id = request.json.get("tank_id")
    if not tank_id:
        return jsonify({"error": "tank_id required"}), 400
    tank = SolutionTanks.query.filter_by(tank_id=tank_id).first()
    if tank:
        tank.current_volume_ml = tank.capacity_ml
        tank.last_alert_sent = 0.0
        tank.consecutive_blocked_attempts = 0
        tank.next_allowed_alert_time = 0.0
        db.session.commit()
        try:
            socketio.emit('tank_levels_updated', {'tank_id': tank.tank_id, 'current_volume_ml': tank.current_volume_ml})
        except Exception:
            pass
        return jsonify(tank.to_json()), 200
    return jsonify({"error": "tank not found"}), 404

def _async_send_report_email_worker(app_obj, include_ml_analysis=True):
    with app_obj.app_context():
        try:
            # Generate PDF natively without test_client
            pdf_bytes = generate_pdf_report_bytes()
            attachments = {"Hydroponics_Report.pdf": pdf_bytes}

            # Generate CSV inline for the digest attachment
            csv_buffer = io.StringIO()
            csv_writer = csv.writer(csv_buffer)
            csv_writer.writerow(["Type", "Timestamp", "Value 1", "Value 2", "Value 3"])
            for d in PHData.query.order_by(PHData.id.desc()).limit(200).all():
                csv_writer.writerow(["pH", d.timestamp.strftime('%Y-%m-%d %H:%M:%S'), d.ph_value, d.water_temp, d.air_temp])
            for d in TDSData.query.order_by(TDSData.id.desc()).limit(200).all():
                csv_writer.writerow(["EC", d.date.strftime('%Y-%m-%d %H:%M:%S'), d.tds_value, d.water_temp, d.air_temp])
            for d in TemperatureHumidityData.query.order_by(TemperatureHumidityData.id.desc()).limit(200).all():
                csv_writer.writerow(["Temp/Hum", d.date.strftime('%Y-%m-%d %H:%M:%S'), d.temperature, d.humidity, ""])
            attachments["Hydroponics_Data.csv"] = csv_buffer.getvalue().encode('utf-8')
            
            selected_photo_path = None
            selected_photo_name = None
            status_note = ""

            historical_photos = PhotoRecord.query.order_by(PhotoRecord.id.desc()).limit(50).all()
            for photo in historical_photos:
                if photo.google_drive_link and os.path.exists(photo.google_drive_link):
                    import cv2
                    img = cv2.imread(photo.google_drive_link)
                    if img is not None and img.mean() >= 10.0:  # Skip pitch-black images
                        selected_photo_path = photo.google_drive_link
                        selected_photo_name = photo.filename
                        status_note = "Daytime snapshot (Standard)."
                        break
            # Fallback to latest photo if all stored photos are dark
            if not selected_photo_path and historical_photos:
                latest = historical_photos[0]
                if latest.google_drive_link and os.path.exists(latest.google_drive_link):
                    selected_photo_path = latest.google_drive_link
                    selected_photo_name = latest.filename


            # Attach the selected image
            if selected_photo_path and os.path.exists(selected_photo_path):
                with open(selected_photo_path, "rb") as f:
                    attachments[selected_photo_name] = f.read()

            yesterday = datetime.utcnow() - timedelta(hours=24)
            abnormalities = EventLog.query.filter(
                EventLog.timestamp >= yesterday, 
                EventLog.category.in_(['WARNING', 'DANGER', 'ALARM'])
            ).order_by(EventLog.timestamp.asc()).all()
            
            if not abnormalities:
                events_html = "<div style='font-family: inherit; background-color: #f0fdf4; border: 1px solid #86efac; border-radius: 8px; padding: 16px; margin-bottom: 24px; color: #166534; font-size: 14px; line-height: 1.5;'>No abnormalities detected in the past 24 hours. The system is operating normally.</div>"
                events_text = "No abnormalities detected in the past 24 hours."
            else:
                # Group repeated warnings by category & message pattern to prevent email clutter
                grouped_events = {}
                for ev in abnormalities:
                    key = f"{ev.category}:{ev.event_id}"
                    if key not in grouped_events:
                        grouped_events[key] = {
                            'category': ev.category,
                            'event_id': ev.event_id,
                            'message': ev.message,
                            'count': 1,
                            'first_seen': ev.timestamp,
                            'last_seen': ev.timestamp
                        }
                    else:
                        grouped_events[key]['count'] += 1
                        grouped_events[key]['last_seen'] = ev.timestamp

                events_html = """
                <h3 style="margin-top: 0; margin-bottom: 12px; font-size: 16px; color: #0f172a; border-bottom: 2px solid #e2e8f0; padding-bottom: 6px; font-weight: 700;">24-Hour Event Summary</h3>
                <div style="background-color: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 16px; margin-bottom: 24px;">
                    <ul style="margin: 0; padding-left: 20px; font-size: 14px; color: #334155; line-height: 1.6;">
                """
                events_text = ""
                for g in grouped_events.values():
                    time_span = g['first_seen'].strftime('%H:%M')
                    if g['count'] > 1:
                        time_span = f"{g['first_seen'].strftime('%H:%M')} – {g['last_seen'].strftime('%H:%M')} ({g['count']} occurrences)"
                    safe_msg = html.escape(g['message'])
                    badge_color = "# fee2e2" if g['category'] in ('DANGER', 'ALARM') else "#fef3c7"
                    text_color = "#b91c1c" if g['category'] in ('DANGER', 'ALARM') else "#b45309"
                    events_html += f"<li style='margin-bottom: 6px;'><strong style='color: #475569;'>{time_span}</strong> <span style='font-size: 11px; font-weight: 700; padding: 2px 6px; border-radius: 4px; background-color: {badge_color}; color: {text_color}; margin-right: 6px;'>{g['category']}</span> {safe_msg}</li>"
                    events_text += f"- {time_span} [{g['category']}] {g['message']}\n"
                events_html += "</ul></div>"
                
            raw_ph = live_ph_data[-1]["value"] if live_ph_data else None
            raw_tds = live_tds_data[-1]["value"] if live_tds_data else None
            raw_t = live_th_data[-1]["t"] if live_th_data else None
            raw_h = live_th_data[-1]["h"] if live_th_data else None

            ph_val = f"{float(raw_ph):.2f}" if raw_ph is not None else "N/A"
            tds_val = f"{float(raw_tds):.2f}" if raw_tds is not None else "N/A"
            t_val = f"{float(raw_t):.1f}" if raw_t is not None else "N/A"
            h_val = f"{float(raw_h):.1f}" if raw_h is not None else "N/A"

            cycle_details = grow_cycle_helper.get_active_grow_cycle_details()
            cycle_text = ""
            cycle_html = ""
            if cycle_details and cycle_details.get("active"):
                ml_verif = cycle_details.get("ml_verification", "Pending")
                cycle_text = f"Grow Cycle: Day {cycle_details.get('day')} ({cycle_details.get('phase')} Phase)\nML Verification: {ml_verif}\nAdvice: {cycle_details.get('advice')}\n\n"
                cycle_html = f"""
                <h3 style="margin-top: 0; margin-bottom: 12px; font-size: 16px; color: #0f172a; border-bottom: 2px solid #e2e8f0; padding-bottom: 6px; font-weight: 700;">Grow Cycle Status</h3>
                <div style="background-color: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 16px; margin-bottom: 24px;">
                    <table style="width: 100%; border-collapse: collapse; font-size: 14px;">
                        <tr>
                            <td style="padding: 6px 0; color: #64748b; font-weight: 600; width: 30%;">Current Day:</td>
                            <td style="padding: 6px 0; color: #0f172a; font-weight: 700;">Day {cycle_details.get('day')}</td>
                        </tr>
                        <tr>
                            <td style="padding: 6px 0; color: #64748b; font-weight: 600;">Active Phase:</td>
                            <td style="padding: 6px 0; color: #0f172a; font-weight: 700;">{cycle_details.get('phase')}</td>
                        </tr>
                        <tr>
                            <td style="padding: 6px 0; color: #64748b; font-weight: 600;">Vision Status:</td>
                            <td style="padding: 6px 0; color: #2563eb; font-weight: 700;">{ml_verif}</td>
                        </tr>
                        <tr>
                            <td style="padding: 6px 0; color: #64748b; font-weight: 600; vertical-align: top;">Advice:</td>
                            <td style="padding: 6px 0; color: #334155; line-height: 1.5;">{cycle_details.get('advice')}</td>
                        </tr>
                    </table>
                </div>
                """

            # Solution tank checks for Daily Digest
            tanks = SolutionTanks.query.all()
            empty_tanks = [t.name for t in tanks if t.current_volume_ml <= 0]
            low_tanks = [t.name for t in tanks if 0 < t.current_volume_ml < t.capacity_ml * 0.1]
            
            tank_text = ""
            tank_html = ""
            if empty_tanks:
                names_str = ", ".join(empty_tanks)
                tank_text += f"CRITICAL WARNING: The following solution tanks are EMPTY: {names_str}. Refill immediately!\n\n"
                tank_html += f'<div style="font-family: inherit; background-color: #fef2f2; border: 1px solid #f87171; border-radius: 8px; padding: 16px; margin-bottom: 24px; color: #991b1b; font-size: 14px; line-height: 1.5;"><strong>Critical Warning:</strong> The following solution tanks are EMPTY: <span style="font-weight: 700;">{names_str}</span>. Dosing pumps are blocked; refill immediately to resume normal operation.</div>'
            if low_tanks:
                names_str = ", ".join(low_tanks)
                tank_text += f"Refill Advisory: The following solution tanks are critically low (< 10%): {names_str}.\n\n"
                tank_html += f'<div style="font-family: inherit; background-color: #eef2ff; border: 1px solid #818cf8; border-radius: 8px; padding: 16px; margin-bottom: 24px; color: #3730a3; font-size: 14px; line-height: 1.5;"><strong>Refill Advisory:</strong> The following solution tanks are critically low (&lt; 10%): <span style="font-weight: 700;">{names_str}</span>. Please refill them soon.</div>'

            ml_text = ""
            ml_html = ""
            if include_ml_analysis:
                try:
                    from camera_ml import detect_plant_stage
                    ml_res = detect_plant_stage()
                    if ml_res:
                        ml_text = f"Machine Learning Vision Analysis:\nDetected Stage: {ml_res.get('stage', 'Unknown')}\n(Annotated analysis frame attached as 'ml_analysis.jpg')\n\n"
                        ml_html = f'<div style="font-family: inherit; background-color: #eff6ff; border: 1px solid #60a5fa; border-radius: 8px; padding: 16px; margin-bottom: 24px; color: #1e40af; font-size: 14px; line-height: 1.5;"><strong>Machine Learning Vision Analysis:</strong><br>Detected Stage: <span style="font-weight: 700;">{ml_res.get("stage", "Unknown")}</span><br>Annotated frame (YOLO bounding boxes or HSV leaf segmenter overlay) is attached as <code>ml_analysis.jpg</code>.</div>'
                        
                        annotated_path = ml_res.get("annotated_filepath")
                        if annotated_path and os.path.exists(annotated_path):
                            try:
                                  with open(annotated_path, "rb") as f:
                                      attachments["ml_analysis.jpg"] = f.read()
                            except Exception as read_img_e:
                                  print(f"DEBUG: Failed to read annotated ML frame for attachment: {read_img_e}")
                except Exception as ml_e:
                    print(f"DEBUG: ML Analysis skipped due to error: {ml_e}")

            body_text = f"Daily System Digest\n\n{tank_text}{ml_text}{cycle_text}Abnormalities (Past 24h):\n{events_text}\n\nCurrent Sensor Readings:\npH: {ph_val}\nEC: {tds_val}\nTemp: {t_val}C\nHumidity: {h_val}%\n\nCamera Status: {status_note}"
            body_html = f"""
            {tank_html}
            {ml_html}
            {cycle_html}
            {events_html}
            <h3 style="margin-top: 0; margin-bottom: 12px; font-size: 16px; color: #0f172a; border-bottom: 2px solid #e2e8f0; padding-bottom: 6px; font-weight: 700;">Current Sensor Readings</h3>
            <div style="background-color: #ffffff; border: 1px solid #e2e8f0; border-radius: 8px; overflow: hidden; margin-bottom: 24px;">
                <table style="width: 100%; border-collapse: collapse; font-size: 14px;">
                    <thead>
                        <tr style="background-color: #f1f5f9; border-bottom: 1px solid #e2e8f0;">
                            <th style="padding: 10px 16px; text-align: left; font-size: 13px; color: #64748b; font-weight: 600;">Sensor</th>
                            <th style="padding: 10px 16px; text-align: right; font-size: 13px; color: #64748b; font-weight: 600;">Value</th>
                        </tr>
                    </thead>
                    <tbody>
                        <tr style="border-bottom: 1px solid #e2e8f0;">
                            <td style="padding: 10px 16px; color: #334155; font-weight: 500;">pH Level</td>
                            <td style="padding: 10px 16px; text-align: right; color: #0f172a; font-weight: 700;">{ph_val}</td>
                        </tr>
                        <tr style="border-bottom: 1px solid #e2e8f0;">
                            <td style="padding: 10px 16px; color: #334155; font-weight: 500;">Electrical Conductivity (EC)</td>
                            <td style="padding: 10px 16px; text-align: right; color: #0f172a; font-weight: 700;">{tds_val} mS/cm</td>
                        </tr>
                        <tr style="border-bottom: 1px solid #e2e8f0;">
                            <td style="padding: 10px 16px; color: #334155; font-weight: 500;">Water Temperature</td>
                            <td style="padding: 10px 16px; text-align: right; color: #0f172a; font-weight: 700;">{t_val}&deg;C</td>
                        </tr>
                        <tr>
                            <td style="padding: 10px 16px; color: #334155; font-weight: 500;">Air Humidity</td>
                            <td style="padding: 10px 16px; text-align: right; color: #0f172a; font-weight: 700;">{h_val}%</td>
                        </tr>
                    </tbody>
                </table>
            </div>
            <p style="font-size: 13px; color: #64748b; margin-top: 16px;"><strong>Camera Status:</strong> {status_note}</p>
            """
            
            success, msg = sensor_monitor.send_report("Daily System Digest", body_text, attachments, html_body=body_html)
            if not success:
                db.session.rollback()
                log_event("EMAIL_ERROR", "ERROR", f"Report email dispatch failed: {msg}")
                return False, msg
            return True, "Email sent successfully"
        except Exception as e:
            db.session.rollback()
            log_event("EMAIL_ERROR", "ERROR", f"Report email dispatch failed: {str(e)}")
            return False, str(e)
        finally:
            db.session.remove()

@app.route("/send_report_email", methods=["POST"])
def send_report_email_route():
    app_obj = current_app._get_current_object()
    default_include_ml = not app_obj.config.get('TESTING', False)
    include_ml = default_include_ml
    try:
        data = request.get_json(silent=True) or {}
        if isinstance(data, dict):
            include_ml = data.get("include_ml_analysis", default_include_ml)
    except Exception:
        pass
    
    threading.Thread(target=_async_send_report_email_worker, args=(app_obj, include_ml), daemon=True).start()
    return jsonify({"message": "Report email generation and sending started in background."}), 200

@app.route("/get_grow_cycle_status", methods=["GET"])
def get_grow_cycle_status_route():
    try:
        details = grow_cycle_helper.get_active_grow_cycle_details()
        return jsonify(details), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/generate_timelapse", methods=["POST"])
def generate_timelapse_route():
    try:
        threading.Thread(target=generate_timelapse, daemon=True).start()
        return jsonify({"message": "Time-lapse generation started in background"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/get_timelapse", methods=["GET"])
def get_timelapse_route():
    try:
        video_path = os.path.join(PHOTO_DIRECTORY, "timelapse.mp4")
        if os.path.exists(video_path):
            return send_file(video_path, mimetype='video/mp4')
        return jsonify({"error": "Time-lapse not found. Please generate one first."}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500

def process_status_mail_check():
    ph_val = round(live_ph_data[-1]['value'], 2) if live_ph_data and live_ph_data[-1]['status'] == "OK" and live_ph_data[-1]['value'] is not None else None
    tds_val = round(live_tds_data[-1]['value'], 2) if live_tds_data and live_tds_data[-1]['status'] == "OK" and live_tds_data[-1]['value'] is not None else None
    t_val = round(live_th_data[-1]['t'], 1) if live_th_data and live_th_data[-1]['status'] == "OK" and live_th_data[-1]['t'] is not None else None
    h_val = round(live_th_data[-1]['h'], 1) if live_th_data and live_th_data[-1]['status'] == "OK" and live_th_data[-1]['h'] is not None else None

    if not any(v is not None for v in (ph_val, tds_val, t_val, h_val)):
        return

    cycle_details = grow_cycle_helper.get_active_grow_cycle_details()
    cycle_limits = cycle_details.get("limits", {}) if cycle_details and cycle_details.get("active") else {}

    import db_cache
    limits = db_cache.get_sensor_limits()
    l_ph_db = limits.get("ph")
    l_tds_db = limits.get("tds")
    l_temp = limits.get("temperature")
    l_hum = limits.get("humidity")

    # Respect Control Mode: Use active grow cycle preset limits ONLY when Autonomous mode is ON (status.state == True).
    # When in Manual mode, use custom DB SensorLimits so logs match the UI.
    status = db_cache.get_plant_status()
    is_auto = status.get("state", False)

    if is_auto and ("ph" in cycle_limits and cycle_limits["ph"]):
        ph_range = cycle_limits["ph"]
    else:
        ph_range = {'min': l_ph_db["min"], 'max': l_ph_db["max"]} if l_ph_db and l_ph_db.get("active") else None

    if is_auto and ("ec" in cycle_limits and cycle_limits["ec"]):
        tds_range = cycle_limits["ec"]
    else:
        tds_range = {'min': l_tds_db["min"], 'max': l_tds_db["max"]} if l_tds_db and l_tds_db.get("active") else None
    temp_range = {'min': l_temp["min"], 'max': l_temp["max"]} if l_temp and l_temp.get("active") else None
    hum_range = {'min': l_hum["min"], 'max': l_hum["max"]} if l_hum and l_hum.get("active") else None

    sensor_monitor.check_sensor_reading('ph', ph_val, ph_range, min_consecutive=10)
    sensor_monitor.check_sensor_reading('tds', tds_val, tds_range, min_consecutive=10)
    sensor_monitor.check_sensor_reading('temperature', t_val, temp_range, min_consecutive=10)
    sensor_monitor.check_sensor_reading('humidity', h_val, hum_range, min_consecutive=10)




@app.route("/status_mail", methods=["POST"])
def check_status_mail_route():
    try:
        process_status_mail_check()
        return jsonify({"message": "Mail Check Complete"}), 200
    except Exception as e: return jsonify({"error": str(e)}), 500

@app.route("/get_ph_history")
def g_ph_h():
    d = PHData.query.order_by(PHData.id.desc()).limit(50).all()
    return jsonify({"ph_data": [x.to_json() for x in reversed(d)]})

@app.route("/get_tds_history")
def g_tds_h():
    d = TDSData.query.order_by(TDSData.id.desc()).limit(50).all()
    return jsonify({"tds_data": [x.to_json() for x in reversed(d)]})

@app.route("/get_temperature_humidity_history")
def g_th_h():
    d = TemperatureHumidityData.query.order_by(TemperatureHumidityData.id.desc()).limit(50).all()
    return jsonify({"temperature_humidity_data": [x.to_json() for x in reversed(d)]})

@app.route("/delete_temperature_humidity_data", methods=["POST"])
def del_th_data():
    try:
        TemperatureHumidityData.query.delete()
        db.session.commit()
        return jsonify({"message": "Data cleared"}), 200
    except Exception as e: return jsonify({"error": str(e)}), 500

@app.route("/delete_moisture_data", methods=["POST"])
def del_m_data():
    try:
        MoistureSensorData.query.delete()
        db.session.commit()
        return jsonify({"message": "Data cleared"}), 200
    except Exception as e: return jsonify({"error": str(e)}), 500

@app.route("/delete_tds_data", methods=["POST"])
def del_tds_data():
    try:
        TDSData.query.delete()
        db.session.commit()
        return jsonify({"message": "Data cleared"}), 200
    except Exception as e: return jsonify({"error": str(e)}), 500

@app.route("/delete_ph_data", methods=["POST"])
def del_ph_data():
    try:
        PHData.query.delete()
        db.session.commit()
        return jsonify({"message": "Data cleared"}), 200
    except Exception as e: return jsonify({"error": str(e)}), 500

@app.route("/get_email_config", methods=["GET"])
def get_email_config():
    try:
        if not os.path.exists("email_config.json"):
            return jsonify({"sender_email": "", "receiver_email": "", "recipient_email": "", "has_password": False}), 200
        with open("email_config.json", "r") as f: config = json.load(f)
        return jsonify({"sender_email": config.get("sender_email", ""), "receiver_email": config.get("receiver_email", ""), "recipient_email": config.get("recipient_email", config.get("receiver_email", "")), "has_password": bool(config.get("sender_password", ""))}), 200
    except Exception as e: return jsonify({"error": str(e)}), 500

@app.route("/update_email_config", methods=["POST"])
def update_email_config():
    try:
        data = request.json
        rec = data.get("recipient_email") or data.get("receiver_email") or ""
        new_config = {"smtp_server": "smtp.gmail.com", "smtp_port": 587, "sender_email": data.get("sender_email", ""), "receiver_email": rec, "recipient_email": rec, "sender_password": data.get("sender_password", "")}
        if os.path.exists("email_config.json"):
            with open("email_config.json", "r") as f: old_config = json.load(f)
            new_config["smtp_server"] = old_config.get("smtp_server", "smtp.gmail.com")
            new_config["smtp_port"] = old_config.get("smtp_port", 587)
            if not new_config["sender_password"]:
                new_config["sender_password"] = old_config.get("sender_password", "")
        with open("email_config.json", "w") as f: json.dump(new_config, f, indent=4)
        sensor_monitor.load_config()
        return jsonify({"message": "Configuration saved successfully"}), 200
    except Exception as e: return jsonify({"error": str(e)}), 500

@app.route("/get_system_config", methods=["GET"])
def get_system_config():
    try:
        config_path = "system_config.json"
        if not os.path.exists(config_path):
            return jsonify({"manual_location": None}), 200
        with open(config_path, "r") as f: config = json.load(f)
        return jsonify(config), 200
    except Exception as e: return jsonify({"error": str(e)}), 500

@app.route("/update_system_config", methods=["POST"])
def update_system_config():
    try:
        data = request.json
        config_path = "system_config.json"
        config = {}
        if os.path.exists(config_path):
            with open(config_path, "r") as f: config = json.load(f)
        
        config.update(data)
        dosing.save_system_config(config)
        return jsonify({"message": "System configuration updated"}), 200
    except Exception as e: return jsonify({"error": str(e)}), 500

@app.route("/api/dosing_config", methods=["GET", "POST"])
def dosing_config():
    try:
        config_path = "system_config.json"
        config = {}
        if os.path.exists(config_path):
            with open(config_path, "r") as f:
                config = json.load(f)
                
        keys = [
            "reservoir_volume_l", "pump_flow_rate_ml_per_sec", "max_dose_time_sec",
            "cooldown_minutes", "nutrient_gap_seconds", "dry_run_mode", "min_dose_time_sec",
            "nutrient_a_volume_ml", "nutrient_b_volume_ml", "ph_up_volume_ml", "ph_down_volume_ml",
            "nutrient_a_capacity_ml", "nutrient_b_capacity_ml", "ph_up_capacity_ml", "ph_down_capacity_ml"
        ]
        
        if request.method == "POST":
            data = request.json
            for k in keys:
                if k in data:
                    config[k] = data[k]
            dosing.save_system_config(config)

                
            tank_map = {
                1: {"volume": "nutrient_a_volume_ml", "capacity": "nutrient_a_capacity_ml"},
                2: {"volume": "nutrient_b_volume_ml", "capacity": "nutrient_b_capacity_ml"},
                3: {"volume": "ph_up_volume_ml", "capacity": "ph_up_capacity_ml"},
                4: {"volume": "ph_down_volume_ml", "capacity": "ph_down_capacity_ml"}
            }
            for t_id, fields in tank_map.items():
                tank = SolutionTanks.query.filter_by(tank_id=t_id).first()
                if not tank:
                    tank = SolutionTanks(tank_id=t_id, name=f"Tank {t_id}", capacity_ml=5000.0, current_volume_ml=5000.0)
                    db.session.add(tank)
                    
                v_key = fields["volume"]
                c_key = fields["capacity"]
                if v_key in data:
                    tank.current_volume_ml = float(data[v_key])
                    if tank.current_volume_ml > 0:
                        tank.last_alert_sent = 0.0
                        tank.consecutive_blocked_attempts = 0
                        tank.next_allowed_alert_time = 0.0
                    if c_key not in data:
                        tank.capacity_ml = float(data[v_key])
                if c_key in data:
                    tank.capacity_ml = float(data[c_key])
            db.session.commit()
            
            return jsonify({"message": "Dosing configuration updated"}), 200
            
        tanks = {t.tank_id: t for t in SolutionTanks.query.all()}
        def get_tank_info(t_id):
            t = tanks.get(t_id)
            return (t.capacity_ml if t else 5000.0, t.current_volume_ml if t else 5000.0)
            
        nut_a_cap, nut_a_vol = get_tank_info(1)
        nut_b_cap, nut_b_vol = get_tank_info(2)
        ph_u_cap, ph_u_vol = get_tank_info(3)
        ph_d_cap, ph_d_vol = get_tank_info(4)
            
        return jsonify({
            "reservoir_volume_l": config.get("reservoir_volume_l", 50.0),
            "pump_flow_rate_ml_per_sec": config.get("pump_flow_rate_ml_per_sec", 1.0),
            "max_dose_time_sec": config.get("max_dose_time_sec", 30.0),
            "cooldown_minutes": config.get("cooldown_minutes", 15),
            "nutrient_gap_seconds": config.get("nutrient_gap_seconds", 10),
            "dry_run_mode": config.get("dry_run_mode", False),
            "min_dose_time_sec": config.get("min_dose_time_sec", 2.0),
            "nutrient_a_capacity_ml": nut_a_cap,
            "nutrient_a_volume_ml": nut_a_vol,
            "nutrient_b_capacity_ml": nut_b_cap,
            "nutrient_b_volume_ml": nut_b_vol,
            "ph_up_capacity_ml": ph_u_cap,
            "ph_up_volume_ml": ph_u_vol,
            "ph_down_capacity_ml": ph_d_cap,
            "ph_down_volume_ml": ph_d_vol
        }), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# --- PRESET MANAGEMENT ENDPOINTS ---

def parse_and_build_stages_json(data):
    """
    Parses incoming request payload for preset CRUD operations,
    normalizes stage dictionaries, calculates cumulative start_day,
    and returns a serialized JSON string.
    """
    if not isinstance(data, dict):
        data = {}

    # Extract stages dictionary (support data["stages"] or root payload keys)
    stages_input = data.get("stages") if isinstance(data.get("stages"), dict) else data

    # Determine phase keys (Canonical 3-Phase vs Legacy Fallback)
    has_canonical = any(k in stages_input for k in ["Seedling", "Harvesting", "Harvest", "Germination"])
    has_legacy = any(k in stages_input for k in ["Flowering", "Maturity"]) and not has_canonical

    if has_legacy:
        phase_keys = ["Vegetative", "Flowering", "Maturity"]
    else:
        phase_keys = ["Seedling", "Vegetative", "Harvesting"]

    default_durations = {
        "Seedling": 10,
        "Vegetative": 25,
        "Harvesting": 20,
        "Germination": 7,
        "Flowering": 30,
        "Maturity": 20
    }

    parsed_stages = {}
    current_start_day = 0

    for key in phase_keys:
        stage_data = stages_input.get(key, {})
        if not isinstance(stage_data, dict):
            stage_data = {}

        formatted_stage = dict(stage_data)

        # Retrieve or compute duration_days
        duration_days = formatted_stage.get("duration_days")
        if duration_days is None:
            duration_days = default_durations.get(key, 14)
        else:
            try:
                duration_days = int(duration_days)
            except (ValueError, TypeError):
                duration_days = default_durations.get(key, 14)

        formatted_stage["duration_days"] = duration_days
        formatted_stage["start_day"] = current_start_day

        current_start_day += duration_days
        parsed_stages[key] = formatted_stage

    # Include any custom/extra stage keys provided in payload
    reserved_keys = {"name", "image_url", "image", "id", "stages"}
    for key, stage_data in stages_input.items():
        if key not in parsed_stages and isinstance(stage_data, dict) and key not in reserved_keys:
            formatted_stage = dict(stage_data)
            duration = formatted_stage.get("duration_days", 14)
            try:
                duration = int(duration)
            except (ValueError, TypeError):
                duration = 14
            formatted_stage["duration_days"] = duration
            formatted_stage["start_day"] = current_start_day
            current_start_day += duration
            parsed_stages[key] = formatted_stage

    return json.dumps(parsed_stages)

@app.route('/api/presets', methods=['GET', 'POST'])
def manage_presets():
    if request.method == 'GET':
        presets = PlantPreset.query.filter_by(is_hidden=False).all()
        return jsonify([p.to_json() for p in presets])
        
    elif request.method == 'POST':
        data = request.json or {}
        image_url = data.get('image_url', '/images/logo.jpg')
        if not image_url or not image_url.strip():
            image_url = '/images/logo.jpg'
            
        stages_json = parse_and_build_stages_json(data)
            
        new_preset = PlantPreset(
            name=data.get('name', 'Custom Plant'),
            image_url=image_url,
            stages_json=stages_json,
            is_continuous_harvest=data.get('is_continuous_harvest', False)
        )
        db.session.add(new_preset)
        db.session.commit()
        db.session.add(PresetAuditLog(preset_name=new_preset.name, action="Created"))
        db.session.commit()
        return jsonify({"message": "Preset added successfully"}), 201

@app.route('/api/presets/<preset_id>', methods=['PUT', 'DELETE'])
def manage_preset(preset_id):
    try:
        preset_id = int(preset_id)
    except (ValueError, TypeError):
        return jsonify({"error": "Invalid preset ID format."}), 404
    preset = db.session.get(PlantPreset, preset_id)
    if not preset:
        abort(404)
    
    if request.method == 'PUT':
        data = request.json or {}
        preset.name = data.get('name', preset.name)
        preset.image_url = data.get('image_url', preset.image_url)
        preset.stages_json = parse_and_build_stages_json(data)
        if 'is_continuous_harvest' in data:
            preset.is_continuous_harvest = data.get('is_continuous_harvest')
        db.session.commit()
        db.session.add(PresetAuditLog(preset_name=preset.name, action="Updated"))
        db.session.commit()
        return jsonify({"message": "Preset updated"}), 200
        
    elif request.method == 'DELETE':
        # Check if preset is active
        status = PlantStageStatus.query.first()
        if status and status.plant_name == preset.name:
            return jsonify({"error": "Cannot delete a preset that is currently active"}), 400

        name = preset.name
        action_log = "Deleted"
        if preset.is_builtin:
            preset.is_hidden = True
            action_log = "Hidden"
        else:
            db.session.delete(preset)
            
        db.session.commit()
        db.session.add(PresetAuditLog(preset_name=name, action=action_log))
        db.session.commit()
        return jsonify({"message": f"Preset {action_log.lower()}"}), 200

@app.route('/api/preset_logs', methods=['GET'])
def get_preset_logs():
    logs = PresetAuditLog.query.order_by(PresetAuditLog.timestamp.desc()).limit(50).all()
    return jsonify([log.to_json() for log in logs])

@app.route('/update_grow_cycle_progress', methods=['POST'])
@app.route('/update-grow-cycle-progress', methods=['POST'])
def update_grow_cycle_progress():
    s = PlantStageStatus.query.first()
    if not s or not s.plant_name:
        return jsonify({"error": "No active growth cycle found."}), 400

    data = request.get_json(silent=True) or {}
    if not isinstance(data, dict):
        return jsonify({"error": "Invalid JSON payload."}), 400

    day_val = data.get("day")
    if day_val is None:
        day_val = data.get("current_day")
    if day_val is None:
        day_val = data.get("days_since_planting")

    if day_val is None:
        return jsonify({"error": "Day parameter is required."}), 400

    try:
        target_day = int(day_val)
        if target_day < 0:
            return jsonify({"error": "Day must be a non-negative integer."}), 400
    except (ValueError, TypeError):
        return jsonify({"error": "Day must be a valid non-negative integer."}), 400

    target_stage = data.get("plant_stage") or data.get("phase") or data.get("stage")

    s.cycle_start_date = datetime.utcnow() - timedelta(days=target_day)

    if target_stage and str(target_stage).strip():
        s.plant_stage = str(target_stage).strip()
    else:
        cycle_info = grow_cycle_helper.get_active_grow_cycle_details()
        if cycle_info and cycle_info.get("scheduled_phase") and cycle_info.get("scheduled_phase") not in ["None", "Unknown", "Error"]:
            s.plant_stage = cycle_info["scheduled_phase"]

    db.session.commit()

    cycle_details = grow_cycle_helper.get_active_grow_cycle_details()
    socketio.emit('grow_cycle_update', cycle_details)
    
    try:
        from camera_ml import detect_plant_stage
        threading.Thread(target=detect_plant_stage, daemon=True).start()
    except Exception as e:
        print(f"Error triggering ML analysis: {e}")

    return jsonify({
        "status": "success",
        "message": "Grow cycle progress updated successfully",
        "current_day": target_day,
        "plant_stage": s.plant_stage,
        "cycle_start_date": s.cycle_start_date.isoformat() if s.cycle_start_date else None,
        "cycle": cycle_details
    }), 200

@app.route('/api/cycle/new', methods=['POST'])
def start_new_cycle():
    try:
        csv_path, json_path = generate_cycle_reports()
        
        config_path = "system_config.json"
        with open(config_path, "r") as f:
            config = json.load(f)
        recipient_email = config.get("recipient_email")
        if not recipient_email:
            return jsonify({"error": "No recipient_email configured in system_config.json"}), 500
            
        try:
            attachments_dict = {}
            for path in [csv_path, json_path]:
                if os.path.exists(path):
                    with open(path, "rb") as f:
                        attachments_dict[os.path.basename(path)] = f.read()

            success, msg = sensor_monitor.send_report(
                "Cycle Reports",
                "Please find the attached cycle reports.",
                attachments=attachments_dict
            )
            if not success:
                raise Exception(msg)
        except Exception as e:
            print(f"Failed to send email: {e}")
            return jsonify({"error": f"Email sending failed: {str(e)}"}), 500
            
        # Email succeeded, archive data
        PHData.query.filter_by(archived=False).update({"archived": True})
        TDSData.query.filter_by(archived=False).update({"archived": True})
        TemperatureHumidityData.query.filter_by(archived=False).update({"archived": True})
        
        status = PlantStageStatus.query.first()
        if status:
            status.cycle_start_date = datetime.utcnow()
            preset = PlantPreset.query.filter_by(name=status.plant_name).first()
            if preset:
                stages = json.loads(preset.stages_json)
                sorted_stages = sorted(stages.items(), key=lambda x: x[1].get('start_day', 0))
                if sorted_stages:
                    status.plant_stage = sorted_stages[0][0]
                    
        db.session.commit()
        return jsonify({"message": "Cycle reports sent and data archived successfully."}), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


# --- SPA SERVING FALLBACK ROUTE ---
@app.route('/', defaults={'path': ''}, methods=["GET"])
@app.route('/<path:path>', methods=["GET"])
def serve_spa(path):
    if request.method != "GET" or path.startswith("api/") or path.startswith("get_") or path.startswith("pump/") or path.startswith("sensor/") or path.startswith("update_") or path.startswith("set_"):
        abort(404)
    full_path = os.path.join(app.static_folder, path)
    if path != "" and os.path.exists(full_path) and os.path.isfile(full_path):
        return send_from_directory(app.static_folder, path)
    index_path = os.path.join(app.static_folder, 'index.html')
    if os.path.exists(index_path):
        return send_file(index_path)
    return jsonify({"message": "HydroAgrix API Server Operational"}), 200


@app.route('/api/grow_cycle/change_phase', methods=['POST'])
def change_grow_cycle_phase():
    s = PlantStageStatus.query.first()
    if not s or not s.plant_name:
        return jsonify({"error": "No active growth cycle found."}), 400

    data = request.json or {}
    direction = data.get("direction") # "next" or "prev"
    target_phase = data.get("phase")

    preset = PlantPreset.query.filter_by(name=s.plant_name).first()
    if not preset:
        return jsonify({"error": f"Plant preset '{s.plant_name}' not found."}), 404

    try:
        stages = json.loads(preset.stages_json)
    except Exception:
        return jsonify({"error": "Failed to parse preset stages."}), 500

    sorted_stages = sorted(stages.items(), key=lambda x: x[1].get('start_day', 0))
    stage_names = [st[0] for st in sorted_stages]

    if not stage_names:
        return jsonify({"error": "Preset has no defined stages."}), 400

    current_stage = s.plant_stage or stage_names[0]
    try:
        curr_idx = stage_names.index(current_stage)
    except ValueError:
        curr_idx = 0

    if target_phase:
        if target_phase in stage_names:
            new_idx = stage_names.index(target_phase)
        else:
            return jsonify({"error": f"Stage '{target_phase}' not valid for preset."}), 400
    elif direction == "next":
        new_idx = min(curr_idx + 1, len(stage_names) - 1)
    elif direction == "prev":
        new_idx = max(curr_idx - 1, 0)
    else:
        return jsonify({"error": "Invalid direction or target phase specified."}), 400

    new_stage = stage_names[new_idx]
    new_stage_info = stages[new_stage]
    target_start_day = new_stage_info.get('start_day', 1)

    s.plant_stage = new_stage
    s.cycle_start_date = datetime.utcnow() - timedelta(days=max(0, target_start_day - 1))
    db.session.commit()

    log_event(
        "GROW_CYCLE_PHASE_CHANGED", "INFO",
        f"Growth cycle phase manually changed from '{current_stage}' to '{new_stage}' for plant '{s.plant_name}'."
    )
    
    sensor_monitor.send_email_alert("SYSTEM", f"Growth cycle phase manually updated to '{new_stage}' for '{s.plant_name}'.", "INFO", True)

    details = grow_cycle_helper.get_active_grow_cycle_details()
    socketio.emit('grow_cycle_update', details)
    
    try:
        from camera_ml import detect_plant_stage
        threading.Thread(target=detect_plant_stage, daemon=True).start()
    except Exception as e:
        print(f"Error triggering ML analysis: {e}")

    return jsonify({
        "message": f"Phase successfully updated to '{new_stage}'",
        "details": details
    }), 200
