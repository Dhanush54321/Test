import os
LOCAL_SIGNALING_URL = "http://localhost:9010"
PRODUCTION_SIGNALING_URL = "https://test-e0et.onrender.com"
ENVIRONMENT = os.getenv("ENVIRONMENT", "production")  

if ENVIRONMENT == "local":
    SIGNALING_SERVER_URL = LOCAL_SIGNALING_URL
else:
    SIGNALING_SERVER_URL = PRODUCTION_SIGNALING_URL
VIDEO_WIDTH = 640
VIDEO_HEIGHT = 480
VIDEO_FPS = 30
CAMERA_INDEX = 0
# print(f"[Config] Environment: {ENVIRONMENT}")
# print(f"[Config] Signaling Server: {SIGNALING_SERVER_URL}")