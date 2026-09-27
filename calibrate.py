"""Three horizontal eye-only dots and optional blink calibration."""
import json
import statistics
import time
from pathlib import Path

import cv2
import numpy as np
import pyautogui

from horizontal_logic import blink_thresholds, calibrate_horizontal
from iris_tracking import IrisTracker

HERE = Path(__file__).resolve().parent


def main():
    cfg = json.loads((HERE / "config.json").read_text(encoding="utf-8"))
    sw, sh = pyautogui.size()
    tracker = IrisTracker(cfg["camera_index"])
    readings = {}
    open_ears = {}
    try:
        cv2.namedWindow("HORIZONTAL IRIS CALIBRATION", cv2.WINDOW_NORMAL)
        cv2.setWindowProperty("HORIZONTAL IRIS CALIBRATION", cv2.WND_PROP_FULLSCREEN,
                              cv2.WINDOW_FULLSCREEN)
        for label, x in (("center", .5), ("left", .18), ("right", .82)):
            values = []
            ears = [[], []]
            started = time.monotonic()
            while time.monotonic() - started < 2.3:
                frame, signal = tracker.read()
                if frame is None:
                    raise RuntimeError("Webcam stopped")
                elapsed = time.monotonic() - started
                canvas = np.full((sh, sw, 3), (22, 29, 45), dtype=np.uint8)
                cv2.circle(canvas, (int(sw * x), int(sh * .48)), 29,
                           (100, 230, 150) if elapsed > .9 else (230, 230, 230), -1)
                cv2.putText(canvas, f"LOOK {label.upper()} WITH ONLY YOUR EYES", (30, sh - 75),
                            cv2.FONT_HERSHEY_SIMPLEX, .8, (255, 255, 255), 2)
                cv2.putText(canvas, "Keep head still. Press Esc to cancel.", (30, sh - 35),
                            cv2.FONT_HERSHEY_SIMPLEX, .62, (205, 230, 255), 2)
                if signal is None:
                    cv2.putText(canvas, "NO FACE", (30, 55), cv2.FONT_HERSHEY_SIMPLEX,
                                .8, (80, 80, 255), 2)
                elif elapsed > .9 and min(signal["left_ear"], signal["right_ear"]) > .045:
                    values.append(signal["eye_x"])
                    ears[0].append(signal["left_ear"])
                    ears[1].append(signal["right_ear"])
                cv2.imshow("HORIZONTAL IRIS CALIBRATION", canvas)
                if cv2.waitKey(1) & 0xFF == 27:
                    print("Calibration cancelled")
                    return
            if len(values) < 8:
                raise ValueError(f"Too few visible iris samples at {label}. Improve light and try again.")
            readings[label] = statistics.median(values)
            open_ears[label] = ears
        profile = calibrate_horizontal(readings)
        closed_ears = [[], []]
        started = time.monotonic()
        while time.monotonic() - started < 2.2:
            frame, signal = tracker.read()
            if frame is None:
                raise RuntimeError("Webcam stopped")
            canvas = np.full((sh, sw, 3), (22, 29, 45), dtype=np.uint8)
            cv2.putText(canvas, "CLOSE BOTH EYES", (max(25, sw // 4), sh // 2),
                        cv2.FONT_HERSHEY_SIMPLEX, 1., (255, 255, 255), 2)
            if signal is not None and time.monotonic() - started > .6:
                closed_ears[0].append(signal["left_ear"])
                closed_ears[1].append(signal["right_ear"])
            cv2.imshow("HORIZONTAL IRIS CALIBRATION", canvas)
            if cv2.waitKey(1) & 0xFF == 27:
                print("Calibration cancelled")
                return
        open_values = [min(statistics.median(open_ears[k][i]) for k in readings) for i in (0, 1)]
        closed_values = ([statistics.median(v) for v in closed_ears]
                         if all(len(v) >= 8 for v in closed_ears) else None)
        profile["closed_thresholds"], profile["blink_reliable"] = blink_thresholds(
            open_values, closed_values, cfg["eye_closed_threshold"])
        (HERE / "calibration.json").write_text(json.dumps(profile, indent=2), encoding="utf-8")
        print("Horizontal iris calibration saved:", profile["span"])
        if not profile["blink_reliable"]:
            print("Blink was not clearly tracked; the app will use dwell selection.")
    finally:
        tracker.close()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, ValueError) as exc:
        print("Calibration failed:", exc)
        raise SystemExit(1)
