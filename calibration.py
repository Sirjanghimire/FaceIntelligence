"""
calibration.py — 9-point gaze calibration.

A dot appears at 9 screen positions. Look at each one and keep your head
comfortable (small head movements are fine — they are part of the model).
The script fits   screen_x, screen_y = f(gaze_x, gaze_y, yaw, pitch)
and saves calibration.json. Then set "cursor_mode": "gaze" in config.json
(or press G inside face_cursor.py).

Press ESC to abort.
"""

import json
import os
import time

import cv2
import numpy as np
import pyautogui

from tracking import FaceTracker

HERE = os.path.dirname(os.path.abspath(__file__))
SETTLE_S = 1.2       # time to move your eyes to the new dot
RECORD_S = 1.2       # time we record samples for
MARGIN = 0.08        # dots stay 8 % away from screen edges


def main():
    with open(os.path.join(HERE, "config.json"), encoding="utf-8") as f:
        cfg = json.load(f)

    sw, sh = pyautogui.size()
    tracker = FaceTracker(cfg["camera_index"])

    win = "calibration"
    cv2.namedWindow(win, cv2.WINDOW_NORMAL)
    cv2.setWindowProperty(win, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)

    xs = [MARGIN, 0.5, 1 - MARGIN]
    ys = [MARGIN, 0.5, 1 - MARGIN]
    targets = [(int(x * sw), int(y * sh)) for y in ys for x in xs]

    features, screen_pts = [], []

    for tx, ty in targets:
        t0 = time.time()
        samples = []
        while True:
            frame, s = tracker.read()
            if frame is None:
                break
            elapsed = time.time() - t0
            canvas = np.zeros((sh, sw, 3), dtype=np.uint8)
            canvas[:] = (20, 20, 20)

            recording = elapsed > SETTLE_S
            colour = (0, 220, 0) if recording else (255, 255, 255)
            cv2.circle(canvas, (tx, ty), 28, colour, -1)
            cv2.circle(canvas, (tx, ty), 6, (20, 20, 20), -1)
            msg = "recording... keep looking" if recording else "look at the dot"
            if s is None:
                msg = "NO FACE"
            cv2.putText(canvas, msg, (40, sh - 50), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (200, 200, 200), 2)

            if recording and s is not None:
                samples.append([s["gaze_x"], s["gaze_y"], s["yaw"], s["pitch"]])

            cv2.imshow(win, canvas)
            if cv2.waitKey(1) & 0xFF == 27:
                print("Aborted.")
                tracker.release()
                cv2.destroyAllWindows()
                return
            if elapsed > SETTLE_S + RECORD_S:
                break

        if len(samples) < 5:
            print(f"Too few samples at {(tx, ty)} — is the camera seeing you? Try again.")
            tracker.release()
            cv2.destroyAllWindows()
            return
        arr = np.array(samples)
        med = np.median(arr, axis=0)                 # median = robust to blinks
        features.append([*med, 1.0])
        screen_pts.append([tx, ty])
        print(f"point {(tx, ty)}  gaze {med[0]:.2f},{med[1]:.2f}  head {med[2]:+.3f},{med[3]:+.3f}")

    F = np.array(features)               # 9 x 5
    P = np.array(screen_pts, dtype=float)  # 9 x 2
    coef_x, *_ = np.linalg.lstsq(F, P[:, 0], rcond=None)
    coef_y, *_ = np.linalg.lstsq(F, P[:, 1], rcond=None)

    pred = np.stack([F @ coef_x, F @ coef_y], axis=1)
    err = np.linalg.norm(pred - P, axis=1)
    print(f"\nMean error {err.mean():.0f} px, worst {err.max():.0f} px  (screen {sw}x{sh})")
    if err.mean() > sw * 0.12:
        print("That is quite high. Better lighting, camera at eye level, and less head movement help.")

    with open(os.path.join(HERE, "calibration.json"), "w", encoding="utf-8") as f:
        json.dump({"coef_x": coef_x.tolist(), "coef_y": coef_y.tolist(),
                   "screen": [sw, sh], "mean_error_px": float(err.mean())}, f, indent=2)
    print("Saved calibration.json.  Set cursor_mode to \"gaze\" or press G in face_cursor.py.")

    tracker.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
