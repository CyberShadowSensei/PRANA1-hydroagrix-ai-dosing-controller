"""Computer Vision & Crop Stage Classifier
Integrates V4L2 USB camera captures, HSV canopy segmentation, and YOLO stage analysis.
"""
import os
import cv2
import time
import base64
import threading
import glob
import numpy as np
from datetime import datetime
from config import app, db, socketio
from models import PhotoRecord, PlantStageStatus

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

def capture_single_frame():
    """
    Temporarily opens the camera, grabs a single stable frame, and releases it.
    """
    print("DEBUG: Capturing single frame on demand")
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        return None
    try:
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        # Flush initial frames to allow USB camera auto-exposure stabilization
        for _ in range(20):
            cap.read()
            time.sleep(0.01)
        
        # Read stable frame with brightness validation
        best_frame = None
        for _ in range(5):
            ret, frame = cap.read()
            if ret and frame is not None:
                best_frame = frame
                if frame.mean() >= 10.0:  # Non-black frame
                    return frame
        return best_frame
    except Exception as e:
        print(f"Error in capture_single_frame: {e}")
    finally:
        cap.release()
    return None


def camera_worker():
    global global_camera, latest_frame, stream_running
    print("DEBUG: Starting Robust Camera Worker (SocketIO Task)")
    while True:
        try:
            if not stream_running:
                # If stream is disabled, release camera to save CPU and heat
                if global_camera is not None:
                    print("DEBUG: Releasing USB Camera to save CPU/heat")
                    global_camera.release()
                    global_camera = None
                socketio.sleep(1.0)
                continue

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
                
                _, buffer = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), 50])
                b64_frame = base64.b64encode(buffer).decode('utf-8')
                socketio.emit('camera_frame', {'image': b64_frame})
                socketio.sleep(0.05)
            else:
                print("DEBUG: Camera frame read error, releasing camera...")
                if global_camera: global_camera.release()
                global_camera = None
                socketio.sleep(2)
        except Exception as e:
            print(f"Camera Worker Error: {e}")
            socketio.sleep(2)

def get_latest_frame():
    with camera_lock:
        if latest_frame is not None and stream_running:
            return latest_frame.copy()
    return capture_single_frame()

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
        annotated_filepath = None
        model = get_ml_model()
        if model is not None:
            results = model(frame, verbose=False)
            if results and len(results[0].boxes) > 0:
                best_idx = results[0].boxes.conf.argmax().item()
                class_id = int(results[0].boxes.cls[best_idx].item())
                detected_stage = results[0].names[class_id]
                print(f"DEBUG: ML Engine detected: {detected_stage}")
                
                try:
                    annotated_frame = results[0].plot()
                    annotated_filename = f"annotated_stage_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
                    annotated_filepath = os.path.join(PHOTO_DIRECTORY, annotated_filename)
                    cv2.imwrite(annotated_filepath, annotated_frame)
                except Exception as plot_e:
                    print(f"DEBUG: Failed to plot YOLO bounding boxes: {plot_e}")
            else:
                print("DEBUG: ML Engine detected no distinct stage (using default).")
        else:
            try:
                hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
                if isinstance(hsv, np.ndarray) and hsv.ndim == 3:
                    h, s, v = hsv[:, :, 0], hsv[:, :, 1], hsv[:, :, 2]
                    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
                    v_clahe = clahe.apply(v)
                    if isinstance(v_clahe, np.ndarray):
                        hsv_clahe = np.dstack([h, s, v_clahe])
                    else:
                        hsv_clahe = hsv
                else:
                    hsv_clahe = frame
                
                mask = cv2.inRange(hsv_clahe, np.array([35, 40, 40]), np.array([85, 255, 255]))
                if isinstance(mask, np.ndarray):
                    green_pixels = np.sum(mask > 0)
                    total_pixels = frame.shape[0] * frame.shape[1] if hasattr(frame, 'shape') and len(frame.shape) >= 2 else 1
                    coverage = (green_pixels / total_pixels) * 100.0
                    if coverage > 50.0:
                        detected_stage = "Flowering"
                    elif coverage > 15.0:
                        detected_stage = "Vegetative"
                    else:
                        detected_stage = "Seedling"
                    
                    try:
                        annotated_frame = frame.copy()
                        cv2.putText(
                            annotated_frame,
                            f"HSV Coverage: {coverage:.1f}% - Stage: {detected_stage}",
                            (10, 30),
                            cv2.FONT_HERSHEY_SIMPLEX,
                            1.0,
                            (0, 255, 0),
                            2
                        )
                        annotated_filename = f"hsv_annotated_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
                        annotated_filepath = os.path.join(PHOTO_DIRECTORY, annotated_filename)
                        cv2.imwrite(annotated_filepath, annotated_frame)
                    except Exception as fallback_draw_e:
                        print(f"DEBUG: Failed to draw fallback text on frame: {fallback_draw_e}")
            except Exception as hsv_e:
                print(f"DEBUG: HSV leaf coverage fallback error: {hsv_e}")
        
        with app.app_context():
            status = PlantStageStatus.query.first()
            if status:
                status.plant_stage = detected_stage
                db.session.commit()
                from grow_cycle_helper import get_active_grow_cycle_details
                socketio.emit('grow_cycle_update', get_active_grow_cycle_details())
                
        return {"stage": detected_stage, "annotated_filepath": annotated_filepath}
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
                print("DEBUG: Plant stage detection completed. Next run in 24 hours.")
        except Exception as e:
            print(f"DEBUG: Plant monitor error: {e}")
        time.sleep(86400)

plant_monitor_thread = _plant_monitor_loop

def start_plant_monitor():
    global plant_monitor_running
    if not plant_monitor_running:
        plant_monitor_running = True
        threading.Thread(target=_plant_monitor_loop, daemon=True).start()

def set_stream_running(state):
    global stream_running
    stream_running = state
