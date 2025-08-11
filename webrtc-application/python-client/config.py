import os
import cv2  # You forgot to import cv2 here

# Signal server configuration (if needed)
LOCAL_SIGNALING_URL = "http://localhost:9010"
PRODUCTION_SIGNALING_URL = "https://test-e0et.onrender.com"

# Set environment: "local" or "production"
ENVIRONMENT = os.getenv("ENVIRONMENT", "production")

if ENVIRONMENT == "local":
    SIGNALING_SERVER_URL = LOCAL_SIGNALING_URL
else:
    SIGNALING_SERVER_URL = PRODUCTION_SIGNALING_URL

# Video settings
VIDEO_WIDTH = 640
VIDEO_HEIGHT = 480
VIDEO_FPS = 30

# Automatically find a working camera index (Linux/Windows/macOS)
def find_camera_index(max_index=5):
    for i in range(max_index):
        cap = cv2.VideoCapture(i)
        if cap.isOpened():
            cap.release()
            return i
    return None  # No camera found

# Set the camera index
CAMERA_INDEX = find_camera_index()

if CAMERA_INDEX is None:
    print("[Config] ❌ No working webcam detected.")
else:
    print(f"[Config] ✅ Using camera index: {CAMERA_INDEX}")

# Optional debug info
print(f"[Config] Environment: {ENVIRONMENT}")
print(f"[Config] Signaling Server: {SIGNALING_SERVER_URL}")
