import cv2

cap = cv2.VideoCapture(0)  # try with 1 if 0 fails
if not cap.isOpened():
    print("Failed to open camera")
else:
    ret, frame = cap.read()
    if ret:
        print("Camera works!")
    else:
        print("Failed to read frame")
    cap.release()
