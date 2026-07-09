import os
import time
import json
import threading
import io
from io import BytesIO
import pytz
from datetime import datetime
import cv2
import requests

from flask import request, jsonify, send_file
from config import app, db, socketio
import hal
from models import LightBulb, MoistureSensorData, TemperatureHumidityData, PhotoRecord, TDSData, PHData, SensorLimits, PlantStageStatus, PumpLog, PlantPreset, PresetAuditLog, EventLog

from sensors import live_ph_data, live_tds_data, live_th_data, fetch_ph, fetch_tds, fetch_th, sensor_monitor, log_event
from dosing import log_pump_action, auto_stop_pump, check_and_adjust_sensors
from camera_ml import PHOTO_DIRECTORY, get_latest_frame, set_stream_running, start_plant_monitor, is_image_dark, generate_timelapse

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
    return jsonify(s.to_json() if s else {}), 200

@app.route("/update_plant_status", methods=["POST"])
def u_plant_status():
    s = PlantStageStatus.query.first()
    if 'state' in request.json: 
        s.state = request.json['state']
        if s.state: start_plant_monitor()
    db.session.commit()
    return jsonify(s.to_json()), 200

@app.route("/set_active_plant", methods=["POST"])
def s_active_plant():
    s = PlantStageStatus.query.first()
    if 'plant_name' in request.json: s.plant_name = request.json['plant_name']
    db.session.commit()
    return jsonify(s.to_json()), 200

@app.route("/get_ph")
def get_ph():
    return jsonify(fetch_ph())

@app.route("/get_tds")
def get_tds():
    return jsonify(fetch_tds())

@app.route("/get_temperature_humidity")
def get_th():
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

@app.route("/pump/all/stop", methods=["POST"])
def stop_all_pumps_route():
    try:
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
def get_latest_photo():
    import glob
    import os
    from flask import send_file
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

@app.route("/api/dosing_events", methods=["GET"])
def get_dosing_events():
    try:
        limit = int(request.args.get("limit", 50))
        # Fetch both automated DOSING events and manual PumpLogs to construct a unified history
        events = EventLog.query.filter_by(category="DOSING").order_by(EventLog.id.desc()).limit(limit).all()
        # Fetch manual pump actions
        manual_pumps = PumpLog.query.filter(PumpLog.trigger_type.like("%Manual%")).order_by(PumpLog.id.desc()).limit(limit).all()
        
        combined = []
        for e in events:
            combined.append({
                "type": "Automatic",
                "action": e.event_id.replace("DOSING_STARTED_", "").replace("_", " "),
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
        return jsonify({x.sensor_type: {"min": x.min_value, "max": x.max_value, "active": x.is_active} for x in l})
    data = request.json
    for k, v in data.items():
        limit = SensorLimits.query.filter_by(sensor_type=k).first()
        if limit:
            limit.min_value = v.get('min', limit.min_value)
            limit.max_value = v.get('max', limit.max_value)
            limit.is_active = v.get('active', limit.is_active)
        else:
            # Create new record if it doesn't exist
            limit = SensorLimits(
                sensor_type=k,
                min_value=v.get('min', 0),
                max_value=v.get('max', 0),
                is_active=v.get('active', False)
            )
            db.session.add(limit)
    db.session.commit()
    return jsonify({"message": "Saved"}), 200

@app.route("/download_database_pdf")
def dl_pdf():
    try:
        from reportlab.lib import colors
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.lib.pagesizes import letter
        buffer = BytesIO(); doc = SimpleDocTemplate(buffer, pagesize=letter); elements = []; styles = getSampleStyleSheet()
        elements.append(Paragraph("IoT Hydroponic System Status Report", styles['Title']))
        ph = PHData.query.order_by(PHData.id.desc()).first(); tds = TDSData.query.order_by(TDSData.id.desc()).first(); th = TemperatureHumidityData.query.order_by(TemperatureHumidityData.id.desc()).first()
        
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
        
        t_summary = Table(summary_data, colWidths=[120, 100, 100, 100]); t_summary.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey), ('GRID', (0, 0), (-1, -1), 1, colors.black)]))
        elements.append(t_summary); doc.build(elements); buffer.seek(0)
        return send_file(buffer, as_attachment=True, download_name="Hydroponics_Report.pdf", mimetype="application/pdf")
    except Exception as e: return str(e), 500

@app.route("/download_database_csv")
def dl_csv():
    try:
        import io; from io import BytesIO; tz = pytz.timezone('Asia/Kolkata'); buf = io.StringIO()
        buf.write("Date,Time,Air_Temp,Air_Hum,pH,pH_Water_Temp,pH_Air_Temp,EC,EC_Water_Temp,EC_Air_Temp\n")
        th_list = TemperatureHumidityData.query.order_by(TemperatureHumidityData.id.desc()).limit(200).all()
        ph_list = PHData.query.order_by(PHData.id.desc()).limit(200).all()
        tds_list = TDSData.query.order_by(TDSData.id.desc()).limit(200).all()
        def get_bucket(dt_obj):
            loc = dt_obj.replace(tzinfo=pytz.UTC).astimezone(tz)
            return loc.replace(second=(loc.second // 10) * 10, microsecond=0)
        rows = {}
        for x in th_list:
            b = get_bucket(x.date)
            if b not in rows: rows[b] = {"t":"","h":"","p":"","p_wt":"","p_at":"","tds":"","tds_wt":"","tds_at":""}
            rows[b]["t"], rows[b]["h"] = x.temperature, x.humidity
        for x in ph_list:
            b = get_bucket(x.timestamp)
            if b not in rows: rows[b] = {"t":"","h":"","p":"","p_wt":"","p_at":"","tds":"","tds_wt":"","tds_at":""}
            rows[b]["p"] = x.ph_value
            rows[b]["p_wt"] = round(x.water_temp, 2) if x.water_temp is not None else ""
            rows[b]["p_at"] = round(x.air_temp, 2) if x.air_temp is not None else ""
        for x in tds_list:
            b = get_bucket(x.date)
            if b not in rows: rows[b] = {"t":"","h":"","p":"","p_wt":"","p_at":"","tds":"","tds_wt":"","tds_at":""}
            rows[b]["tds"] = x.tds_value
            rows[b]["tds_wt"] = round(x.water_temp, 2) if x.water_temp is not None else ""
            rows[b]["tds_at"] = round(x.air_temp, 2) if x.air_temp is not None else ""
        for b in sorted(rows.keys(), reverse=True):
            row = rows[b]
            buf.write(f"{b.strftime('%Y-%m-%d')},{b.strftime('%H:%M:%S')},{row['t']},{row['h']},{row['p']},{row['p_wt']},{row['p_at']},{row['tds']},{row['tds_wt']},{row['tds_at']}\n")
        out = BytesIO(); out.write(buf.getvalue().encode('utf-8')); out.seek(0)
        return send_file(out, as_attachment=True, download_name="report.csv", mimetype="text/csv")
    except Exception as e: return str(e), 400


@app.route("/generate_growth_cycle_report", methods=["POST", "OPTIONS"])
def gen_growth_cycle_report():
    if request.method == "OPTIONS":
        response = jsonify({"status": "OK"})
        response.headers.add("Access-Control-Allow-Origin", "*")
        response.headers.add("Access-Control-Allow-Headers", "Content-Type")
        response.headers.add("Access-Control-Allow-Methods", "POST")
        return response
    try:
        from report_generator import generate_growth_cycle_report
        data = request.json
        if not data or 'start_date' not in data or 'end_date' not in data:
            return jsonify({"error": "start_date and end_date are required"}), 400
        
        # Parse dates
        start_date = datetime.strptime(data['start_date'], '%Y-%m-%dT%H:%M:%S.%fZ')
        end_date = datetime.strptime(data['end_date'], '%Y-%m-%dT%H:%M:%S.%fZ')
        
        pdf_buffer = generate_growth_cycle_report(start_date, end_date)
        return send_file(pdf_buffer, as_attachment=True, download_name="Growth_Cycle_Report.pdf", mimetype="application/pdf")
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.route("/check_and_adjust_sensors", methods=["GET", "POST"])
def ch_a(): check_and_adjust_sensors(); return jsonify({"message": "OK"}), 200

def is_image_dark(image_path, threshold=15):
    """
    Reads the image in grayscale and checks its average pixel intensity.
    If the average value is below the threshold, the image is deemed dark.
    """
    try:
        if not os.path.exists(image_path):
            return True
        img = cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)
        if img is None:
            return True
        avg_brightness = np.mean(img)
        print(f"DEBUG BRIGHTNESS: Image {os.path.basename(image_path)} average brightness = {avg_brightness:.2f} (Threshold = {threshold})")
        return avg_brightness < threshold
    except Exception as e:
        print(f"DEBUG BRIGHTNESS: Failed to evaluate image brightness: {e}")
        return True

@app.route("/send_report_email", methods=["POST"])
def send_report_email_route():
    try:
        with app.test_client() as client:
            pdf_res = client.get('/download_database_pdf')
            csv_res = client.get('/download_database_csv')
        attachments = {"Hydroponics_Report.pdf": pdf_res.data, "Hydroponics_Data.csv": csv_res.data}
        
        selected_photo_path = None
        selected_photo_name = None
        status_note = ""

        # Step 1: Query the latest database photo
        latest_photo = PhotoRecord.query.order_by(PhotoRecord.id.desc()).first()
        
        # Step 2: Check if it is valid and bright
        if latest_photo and os.path.exists(latest_photo.google_drive_link):
            if not is_image_dark(latest_photo.google_drive_link):
                selected_photo_path = latest_photo.google_drive_link
                selected_photo_name = latest_photo.filename
                status_note = "Daytime snapshot (Standard)."
            else:
                print("DEBUG BRIGHTNESS: Latest photo is dark. Attempting live daytime capture...")

        # Step 3: If dark or missing, trigger a fresh daytime camera grab
        if selected_photo_path is None:
            frame = get_latest_frame()
            if frame is not None:
                temp_filename = f"live_digest_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
                temp_path = os.path.join(PHOTO_DIRECTORY, temp_filename)
                cv2.imwrite(temp_path, frame)
                
                # Check if this new frame is bright
                if not is_image_dark(temp_path):
                    # Save to DB and set as attachment
                    new_rec = PhotoRecord(filename=temp_filename, google_drive_link=temp_path)
                    db.session.add(new_rec)
                    db.session.commit()
                    selected_photo_path = temp_path
                    selected_photo_name = temp_filename
                    status_note = "Live 8:00 AM daytime snapshot."
                else:
                    # Clean up the dark live file
                    print("DEBUG BRIGHTNESS: Live captured frame is also dark (lights likely off). Cleaning up...")
                    try:
                        os.remove(temp_path)
                    except Exception:
                        pass

        # Step 4: If live grab is also dark, search DB history for the last known bright daytime capture
        if selected_photo_path is None:
            historical_photos = PhotoRecord.query.order_by(PhotoRecord.id.desc()).limit(50).all()
            for photo in historical_photos:
                if os.path.exists(photo.google_drive_link) and not is_image_dark(photo.google_drive_link):
                    selected_photo_path = photo.google_drive_link
                    selected_photo_name = photo.filename
                    status_note = "Lights currently off. Attaching last known clear daytime capture."
                    break

        # Step 5: Fallback to attaching the latest dark photo if absolutely no bright photo exists
        if selected_photo_path is None and latest_photo and os.path.exists(latest_photo.google_drive_link):
            selected_photo_path = latest_photo.google_drive_link
            selected_photo_name = latest_photo.filename
            status_note = "No bright photos found in history. Attaching latest dark snapshot."

        # Attach the selected image
        if selected_photo_path and os.path.exists(selected_photo_path):
            with open(selected_photo_path, "rb") as f:
                attachments[selected_photo_name] = f.read()

        body = (
            f"Hello! Please find your latest Hydroponics Daily Digest and plant status reports attached.<br><br>"
            f"<b>Camera Status:</b> {status_note}"
        )
        
        success, msg = sensor_monitor.send_report("Daily Hydroponic Digest", body, attachments)
        if success: return jsonify({"message": "Report sent successfully"}), 200
        else: return jsonify({"error": msg}), 500
    except Exception as e: return jsonify({"error": str(e)}), 500

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
    ph_val = live_ph_data[-1]['value'] if live_ph_data and live_ph_data[-1]['status'] == "OK" else None
    tds_val = live_tds_data[-1]['value'] if live_tds_data and live_tds_data[-1]['status'] == "OK" else None
    t_val = live_th_data[-1]['t'] if live_th_data and live_th_data[-1]['status'] == "OK" else None
    h_val = live_th_data[-1]['h'] if live_th_data and live_th_data[-1]['status'] == "OK" else None

    if not any(v is not None for v in (ph_val, tds_val, t_val, h_val)):
        return

    limits = {l.sensor_type: l for l in SensorLimits.query.all()}
    l_ph = limits.get("ph")
    l_tds = limits.get("tds")
    l_temp = limits.get("temperature")
    l_hum = limits.get("humidity")

    if ph_val is not None: 
        sensor_monitor.check_sensor_reading('ph', ph_val, {'min': l_ph.min_value, 'max': l_ph.max_value} if l_ph and l_ph.is_active else None)
    if tds_val is not None: 
        sensor_monitor.check_sensor_reading('tds', tds_val, {'min': l_tds.min_value, 'max': l_tds.max_value} if l_tds and l_tds.is_active else None)
    if t_val is not None:
        sensor_monitor.check_sensor_reading('temperature', t_val, {'min': l_temp.min_value, 'max': l_temp.max_value} if l_temp and l_temp.is_active else None)
    if h_val is not None:
        sensor_monitor.check_sensor_reading('humidity', h_val, {'min': l_hum.min_value, 'max': l_hum.max_value} if l_hum and l_hum.is_active else None)

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
        import json
        if not os.path.exists("email_config.json"):
            return jsonify({"sender_email": "", "receiver_email": "", "has_password": False}), 200
        with open("email_config.json", "r") as f: config = json.load(f)
        return jsonify({"sender_email": config.get("sender_email", ""), "receiver_email": config.get("receiver_email", ""), "has_password": bool(config.get("sender_password", ""))}), 200
    except Exception as e: return jsonify({"error": str(e)}), 500

@app.route("/update_email_config", methods=["POST"])
def update_email_config():
    try:
        import json; data = request.json
        # Start with defaults in case file doesn't exist
        new_config = {"smtp_server": "smtp.gmail.com", "smtp_port": 587, "sender_email": data.get("sender_email", ""), "receiver_email": data.get("receiver_email", ""), "sender_password": data.get("sender_password", "")}
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
        import json
        config_path = "system_config.json"
        if not os.path.exists(config_path):
            return jsonify({"manual_location": None}), 200
        with open(config_path, "r") as f: config = json.load(f)
        return jsonify(config), 200
    except Exception as e: return jsonify({"error": str(e)}), 500

@app.route("/update_system_config", methods=["POST"])
def update_system_config():
    try:
        import json; data = request.json
        config_path = "system_config.json"
        config = {}
        if os.path.exists(config_path):
            with open(config_path, "r") as f: config = json.load(f)
        
        config.update(data)
        with open(config_path, "w") as f: json.dump(config, f, indent=4)
        return jsonify({"message": "System configuration updated"}), 200
    except Exception as e: return jsonify({"error": str(e)}), 500

@app.route("/api/dosing_config", methods=["GET", "POST"])
def dosing_config():
    try:
        import json
        config_path = "system_config.json"
        config = {}
        if os.path.exists(config_path):
            with open(config_path, "r") as f:
                config = json.load(f)
                
        if request.method == "POST":
            data = request.json
            config.update({
                "reservoir_volume_l": data.get("reservoir_volume_l", config.get("reservoir_volume_l", 10.0)),
                "pump_flow_rate_ml_per_sec": data.get("pump_flow_rate_ml_per_sec", config.get("pump_flow_rate_ml_per_sec", 1.0)),
                "max_dose_time_sec": data.get("max_dose_time_sec", config.get("max_dose_time_sec", 30))
            })
            with open(config_path, "w") as f:
                json.dump(config, f, indent=4)
            return jsonify({"message": "Dosing configuration updated"}), 200
            
        return jsonify({
            "reservoir_volume_l": config.get("reservoir_volume_l", 10.0),
            "pump_flow_rate_ml_per_sec": config.get("pump_flow_rate_ml_per_sec", 1.0),
            "max_dose_time_sec": config.get("max_dose_time_sec", 30)
        }), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# --- PRESET MANAGEMENT ENDPOINTS ---

@app.route('/api/presets', methods=['GET', 'POST'])
def manage_presets():
    if request.method == 'GET':
        presets = PlantPreset.query.all()
        return jsonify([p.to_json() for p in presets])
        
    elif request.method == 'POST':
        import json
        data = request.json
        image_url = data.get('image_url', '/images/logo.jpg')
        if not image_url.strip():
            image_url = '/images/logo.jpg'
            
        new_preset = PlantPreset(
            name=data.get('name', 'Custom Plant'),
            image_url=image_url,
            stages_json=json.dumps({
                "Vegetative": data.get("Vegetative", {}),
                "Flowering": data.get("Flowering", {}),
                "Maturity": data.get("Maturity", {})
            })
        )
        db.session.add(new_preset)
        db.session.commit()
        db.session.add(PresetAuditLog(preset_name=new_preset.name, action="Created"))
        db.session.commit()
        return jsonify({"message": "Preset added successfully"}), 201

@app.route('/api/presets/<int:preset_id>', methods=['PUT', 'DELETE'])
def manage_preset(preset_id):
    preset = PlantPreset.query.get_or_404(preset_id)
    import json
    
    if request.method == 'PUT':
        data = request.json
        preset.name = data.get('name', preset.name)
        preset.image_url = data.get('image_url', preset.image_url)
        preset.stages_json = json.dumps({
            "Vegetative": data.get("Vegetative", {}),
            "Flowering": data.get("Flowering", {}),
            "Maturity": data.get("Maturity", {})
        })
        db.session.commit()
        db.session.add(PresetAuditLog(preset_name=preset.name, action="Updated"))
        db.session.commit()
        return jsonify({"message": "Preset updated"}), 200
        
    elif request.method == 'DELETE':
        name = preset.name
        db.session.delete(preset)
        db.session.commit()
        db.session.add(PresetAuditLog(preset_name=name, action="Deleted"))
        db.session.commit()
        return jsonify({"message": "Preset deleted"}), 200

@app.route('/api/preset_logs', methods=['GET'])
def get_preset_logs():
    logs = PresetAuditLog.query.order_by(PresetAuditLog.timestamp.desc()).limit(50).all()
    return jsonify([log.to_json() for log in logs])

