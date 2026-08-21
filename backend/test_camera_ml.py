import pytest
import numpy as np
import cv2
from unittest.mock import MagicMock, patch
import camera_ml

def test_set_stream_running():
    camera_ml.set_stream_running(True)
    assert camera_ml.stream_running is True
    camera_ml.set_stream_running(False)
    assert camera_ml.stream_running is False

def test_camera_worker_throttling_idle():
    with patch('camera_ml.global_camera') as mock_camera, \
         patch('camera_ml.socketio.sleep') as mock_sleep:
        mock_camera.isOpened.return_value = True
        dummy_frame = np.zeros((480, 640, 3), dtype=np.uint8)
        mock_camera.read.return_value = (True, dummy_frame)
        
        camera_ml.stream_running = False
        
        mock_sleep.side_effect = KeyboardInterrupt("Break loop")
        try:
            camera_ml.camera_worker()
        except KeyboardInterrupt:
            pass
            
        mock_sleep.assert_called_with(1.0)

def test_camera_worker_throttling_active():
    with patch('camera_ml.global_camera') as mock_camera, \
         patch('camera_ml.socketio.sleep') as mock_sleep, \
         patch('camera_ml.socketio.emit') as mock_emit, \
         patch.object(cv2, 'imencode', return_value=(True, np.array([1, 2, 3], dtype=np.uint8))):
        mock_camera.isOpened.return_value = True
        dummy_frame = np.zeros((480, 640, 3), dtype=np.uint8)
        mock_camera.read.return_value = (True, dummy_frame)
        
        camera_ml.stream_running = True
        
        mock_sleep.side_effect = KeyboardInterrupt("Break loop")
        try:
            camera_ml.camera_worker()
        except KeyboardInterrupt:
            pass
            
        mock_sleep.assert_called_with(0.05)
        mock_emit.assert_called_once()

def test_clahe_value_channel_normalization():
    # Test real OpenCV CLAHE preprocessing behavior on low-brightness green image
    # Generate a low-brightness green patch (V channel around 35-38, which is below inRange min 40)
    hsv_image = np.zeros((100, 100, 3), dtype=np.uint8)
    hsv_image[:, :, 0] = 50  # Green hue
    hsv_image[:, :, 1] = 150 # High saturation
    hsv_image[:, :, 2] = 36  # Dark Value (below inRange threshold 40)

    # Before CLAHE, inRange should detect 0 green pixels
    mask_before = cv2.inRange(hsv_image, np.array([35, 40, 40]), np.array([85, 255, 255]))
    assert np.sum(mask_before > 0) == 0

    # Apply CLAHE to Value channel as specified in R3
    h, s, v = hsv_image[:, :, 0], hsv_image[:, :, 1], hsv_image[:, :, 2]
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    v_clahe = clahe.apply(v)
    hsv_clahe = np.dstack([h, s, v_clahe])

    # After CLAHE, contrast normalization boosts V channel, allowing green pixel detection
    mask_after = cv2.inRange(hsv_clahe, np.array([35, 40, 40]), np.array([85, 255, 255]))
    assert np.sum(mask_after > 0) > 0
