"""
Step 2 — can MediaPipe see your face, eyes, iris and mouth?

Shows the live numbers the cursor will use. Use this to find YOUR thresholds:
  * open your mouth wide   -> note the MAR value  (set mouth_open_threshold a bit below it)
  * close your eyes        -> note the EAR value  (set blink_threshold a bit above it)
Press Q to quit.
"""
import cv2
from tracking import FaceTracker

tracker = FaceTracker()
print("Face test running. Press Q in the window to quit.")

while True:
    frame, s = tracker.read()
    if frame is None:
        print("Camera stopped")
        break

    tracker.draw_debug(frame, s)

    if s:
        lines = [
            f"yaw   {s['yaw']:+.3f}   pitch {s['pitch']:+.3f}",
            f"gaze  x {s['gaze_x']:.2f}  y {s['gaze_y']:.2f}",
            f"MAR   {s['mar']:.3f}  (mouth)",
            f"EAR   {s['ear']:.3f}  (eyes)",
            f"brow  {s['brow']:.3f}",
        ]
        for i, text in enumerate(lines):
            cv2.putText(frame, text, (10, 30 + i * 28),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)

    cv2.imshow("Face Test  (press Q to quit)", frame)
    if cv2.waitKey(1) & 0xFF == ord("q"):
        break

tracker.release()
cv2.destroyAllWindows()
