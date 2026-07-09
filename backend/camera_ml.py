import os
import cv2
import time
import base64
import threading
import glob
import numpy as np
from datetime import datetime
from config import app, db, socketio
from models import PhotoRecord, PlantStageStatus, PlantPreset, SensorLimits

PHOTO_DIRECTORY = "captured_photos"
os.makedirs(PHOTO_DIRECTORY, exist_ok=True)
MODEL_PATH = 'stage_detect.pt'
plant_monitor_running = False
plant_monitor_lock = threading.Lock()

try:
    from ultralytics import YOLO
except ImportError:
    print("WARNING: ultralytics is not installed. Run 'pip install ultralytics' for ML inference.")
    YOLO = None

global_camera = None
stream_running = False
latest_frame = None
camera_lock = threading.Lock()
ml_model = None

def get_ml_model():
    global ml_model
    if ml_model is None and YOLO is not None and os.path.exists(MODEL_PATH):
        try:
            print(f"DEBUG: Loading YOLO model from {MODEL_PATH}...")
            ml_model = YOLO(MODEL_PATH)
        except Exception as e:
            print(f"DEBUG: Failed to load YOLO model: {e}")
    return ml_model

def camera_worker():
    global global_camera, latest_frame, stream_running
    print("DEBUG: Starting Robust Camera Worker (SocketIO Task)")
    while True:
        try:
            if global_camera is None or not global_camera.isOpened():
                print("DEBUG: Attempting to Open USB Camera (Hiwonder)")
                global_camera = cv2.VideoCapture(0)
                global_camera.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
                global_camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
                if not global_camera.isOpened():
                    print("DEBUG: Camera not found, retrying in 5s...")
                    socketio.sleep(5)
                    continue
                for _ in range(5): global_camera.read()

            ret, frame = global_camera.read()
            if ret:
                with camera_lock:
                    latest_frame = frame.copy()
                
                if stream_running:
                    _, buffer = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), 50])
                    b64_frame = base64.b64encode(buffer).decode('utf-8')
                    socketio.emit('camera_frame', {'image': b64_frame})
            else:
                print("DEBUG: Camera frame read error, releasing camera...")
                if global_camera: global_camera.release()
                global_camera = None
                socketio.sleep(2)
            
            socketio.sleep(0.05)
        except Exception as e:
            print(f"Camera Worker Error: {e}")
            socketio.sleep(2)

def get_latest_frame():
    with camera_lock:
        if latest_frame is not None:
            return latest_frame.copy()
    return None

def detect_plant_stage():
    try:
        frame = get_latest_frame()
        if frame is None: return None
        
        filename = f"plant_stage_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
        filepath = os.path.join(PHOTO_DIRECTORY, filename)
        cv2.imwrite(filepath, frame)
        
        db.session.add(PhotoRecord(filename=filename, google_drive_link=filepath))
        db.session.commit()
        
        detected_stage = "Vegetative"
        model = get_ml_model()
        if model is not None:
            results = model(frame, verbose=False)
            if results and len(results[0].boxes) > 0:
                best_idx = results[0].boxes.conf.argmax().item()
                class_id = int(results[0].boxes.cls[best_idx].item())
                detected_stage = results[0].names[class_id]
                print(f"DEBUG: ML Engine detected: {detected_stage}")
            else:
                print("DEBUG: ML Engine detected no distinct stage (using default).")
        
        with app.app_context():
            import json
            status = PlantStageStatus.query.first()
            if status:
                status.plant_stage = detected_stage
                
                preset = PlantPreset.query.filter_by(name=status.plant_name).first()
                if preset:
                    try:
                        stages = json.loads(preset.stages_json)
                        if detected_stage in stages:
                            stage_limits = stages[detected_stage]
                            
                            ph_lim = SensorLimits.query.filter_by(sensor_type='ph').first()
                            if ph_lim and "ph" in stage_limits:
                                ph_lim.min_value = float(stage_limits["ph"]["min"])
                                ph_lim.max_value = float(stage_limits["ph"]["max"])
                                
                            tds_lim = SensorLimits.query.filter_by(sensor_type='tds').first()
                            if tds_lim and "ec" in stage_limits:
                                tds_lim.min_value = float(stage_limits["ec"]["min"])
                                tds_lim.max_value = float(stage_limits["ec"]["max"])
                    except Exception as parse_e:
                        print(f"DEBUG: Failed to parse PlantPreset limits for ML update: {parse_e}")
                
                db.session.commit()
                
        return detected_stage
    except Exception as e:
        print(f"Detect Plant Stage Error: {e}")
        return None

def is_image_dark(image_path, threshold=15):
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

def generate_timelapse():
    try:
        print("DEBUG: Starting Time-Lapse Generation...")
        images = sorted(glob.glob(os.path.join(PHOTO_DIRECTORY, "*.jpg")))
        if not images:
            print("DEBUG: No images found for time-lapse.")
            return

        frame = cv2.imread(images[0])
        height, width, layers = frame.shape
        video_name = os.path.join(PHOTO_DIRECTORY, "timelapse.mp4")

        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        video = cv2.VideoWriter(video_name, fourcc, 10.0, (width, height))

        for image in images:
            video.write(cv2.imread(image))

        cv2.destroyAllWindows()
        video.release()
        print(f"DEBUG: Time-Lapse successfully generated at {video_name}")
    except Exception as e:
        print(f"DEBUG: Failed to generate time-lapse: {e}")

def _plant_monitor_loop():
    global plant_monitor_running
    while plant_monitor_running:
        try:
            with app.app_context():
                detect_plant_stage()
                print("DEBUG: Plant stage detection completed. Next run in 30 minutes.")
        except Exception as e:
            print(f"DEBUG: Plant monitor error: {e}")
        time.sleep(1800)

def start_plant_monitor():
    global plant_monitor_running
    if not plant_monitor_running:
        plant_monitor_running = True
        threading.Thread(target=_plant_monitor_loop, daemon=True).start()

def set_stream_running(state):
    global stream_running
    stream_running = state
