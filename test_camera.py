"""Step 1 — does the webcam work at all?  Press Q to quit."""
import cv2

camera = cv2.VideoCapture(0)
if not camera.isOpened():
    print("Could not open camera 0. Try changing VideoCapture(0) to (1).")
    raise SystemExit

while True:
    ok, frame = camera.read()
    if not ok:
        print("Could not read a frame from the camera")
        break
    cv2.imshow("Camera Test  (press Q to quit)", cv2.flip(frame, 1))
    if cv2.waitKey(1) & 0xFF == ord("q"):
        break

camera.release()
cv2.destroyAllWindows()
