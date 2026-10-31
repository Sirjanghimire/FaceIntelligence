"""Eyebrow-and-eye controlled on-screen keyboard.

Controls:
    Right wink  -> next key in the row
    Left wink   -> previous key in the row
    Raise eyebrows -> previous row
    Lower eyebrows -> next row
    Hold mouth open -> press the highlighted key
    k           -> show/hide eyebrow tracking overlay
    q           -> quit
    r           -> recalibrate the neutral eyebrow position
"""

import csv
import sys
import time
from datetime import datetime

try:
    import cv2
except ImportError:
    sys.exit("Missing dependency: run  pip install opencv-python")

try:
    import mediapipe as mp
except ImportError:
    sys.exit("Missing dependency: run  pip install mediapipe")

if not hasattr(mp, "solutions"):
    sys.exit("Incompatible MediaPipe version: run  pip install mediapipe==0.10.21 numpy==1.26.4")


CAM_INDEX = 0
WINDOW = "Eye Keyboard"
EYE_CLOSED = 0.23
WINK_MIN_FRAMES = 2
ACTION_COOLDOWN = 0.45
MOUTH_OPEN_THRESHOLD = 0.20
MOUTH_FIRST_PRESS_SECONDS = 2.0
MOUTH_REPEAT_PRESS_SECONDS = 3.0
EYEBROW_FIRST_MOVE_SECONDS = 2.0
EYEBROW_REPEAT_MOVE_SECONDS = 3.0
CALIBRATION_FRAMES = 45
EYEBROW_DEADZONE = 0.055
EYEBROW_RESET_ZONE = 0.08
EYEBROW_NEUTRAL_HOLD_SECONDS = 0.45
EYEBROW_SMOOTHING = 0.25

KEYBOARD = [
    list("QWERTYUIOP"),
    list("ASDFGHJKL"),
    list("ZXCVBNM"),
    ["SPACE", "BACKSPACE", "ENTER"],
]

LEFT_EYE = {"corner_1": 33, "corner_2": 133, "top": 159, "bottom": 145}
RIGHT_EYE = {"corner_1": 362, "corner_2": 263, "top": 386, "bottom": 374}
LEFT_BROW = (70, 63, 105, 66, 107)
RIGHT_BROW = (336, 296, 334, 293, 300)


def eye_openness(landmarks, eye):
    corners = abs(landmarks[eye["corner_2"]].x - landmarks[eye["corner_1"]].x)
    opening = abs(landmarks[eye["top"]].y - landmarks[eye["bottom"]].y)
    return opening / corners if corners else 1.0


def mouth_openness(landmarks):
    mouth_width = abs(landmarks[291].x - landmarks[61].x)
    mouth_height = abs(landmarks[14].y - landmarks[13].y)
    return mouth_height / mouth_width if mouth_width else 0.0


def eyebrow_measurements(landmarks):
    """Measure brow lift relative to upper eyelids, normalized by eye width."""
    left_brow_y = sum(landmarks[index].y for index in LEFT_BROW) / len(LEFT_BROW)
    right_brow_y = sum(landmarks[index].y for index in RIGHT_BROW) / len(RIGHT_BROW)
    left_eye_top_y = landmarks[LEFT_EYE["top"]].y
    right_eye_top_y = landmarks[RIGHT_EYE["top"]].y
    left_eye_width = abs(landmarks[LEFT_EYE["corner_1"]].x - landmarks[LEFT_EYE["corner_2"]].x)
    right_eye_width = abs(landmarks[RIGHT_EYE["corner_1"]].x - landmarks[RIGHT_EYE["corner_2"]].x)
    eye_width = (left_eye_width + right_eye_width) / 2
    left_lift = left_eye_top_y - left_brow_y
    right_lift = right_eye_top_y - right_brow_y
    level = ((left_lift + right_lift) / 2) / eye_width if eye_width > 1e-6 else 0.0
    return {
        "left_brow_y": left_brow_y,
        "right_brow_y": right_brow_y,
        "left_eye_top_y": left_eye_top_y,
        "right_eye_top_y": right_eye_top_y,
        "level": level,
    }


def open_debug_log():
    filename = "eyebrow_debug_" + datetime.now().strftime("%Y%m%d_%H%M%S") + ".csv"
    log_file = open(filename, "w", newline="", encoding="utf-8")
    writer = csv.DictWriter(log_file, fieldnames=[
        "timestamp", "frame", "face_detected", "left_brow_y", "right_brow_y",
        "left_eye_top_y", "right_eye_top_y", "level", "neutral_level", "delta", "deadzone",
        "left_eye_open", "right_eye_open", "mouth_ratio", "selected_row", "selected_col",
        "brow_armed", "neutral_hold_seconds", "action", "status",
    ])
    writer.writeheader()
    log_file.flush()
    print("Debug log:", filename)
    return log_file, writer


def write_debug_log(log_file, writer, frame_number, measurements, neutral_level,
                    selected_row, selected_col, action, status, left_eye_open="",
                    right_eye_open="", mouth_ratio="", brow_armed=False,
                    neutral_hold_seconds=0.0):
    level = measurements.get("level")
    writer.writerow({
        "timestamp": datetime.now().isoformat(timespec="milliseconds"),
        "frame": frame_number,
        "face_detected": bool(measurements),
        **measurements,
        "neutral_level": neutral_level,
        "delta": level - neutral_level if level is not None and neutral_level is not None else "",
        "deadzone": EYEBROW_DEADZONE,
        "left_eye_open": left_eye_open,
        "right_eye_open": right_eye_open,
        "mouth_ratio": mouth_ratio,
        "selected_row": selected_row,
        "selected_col": selected_col,
        "brow_armed": brow_armed,
        "neutral_hold_seconds": neutral_hold_seconds,
        "action": action,
        "status": status,
    })
    log_file.flush()


def draw_keyboard(canvas, selected_row, selected_col):
    height, width = canvas.shape[:2]
    top = int(height * 0.59)
    row_height = max(48, int((height - top - 24) / len(KEYBOARD)))
    gap = 8

    for row_index, row in enumerate(KEYBOARD):
        key_width = (width - gap * (len(row) + 1)) // len(row)
        y1 = top + row_index * row_height + gap
        y2 = y1 + row_height - gap * 2
        for col_index, label in enumerate(row):
            x1 = gap + col_index * (key_width + gap)
            x2 = x1 + key_width
            selected = row_index == selected_row and col_index == selected_col
            color = (0, 205, 255) if selected else (45, 56, 70)
            border = (255, 255, 255) if selected else (105, 120, 135)
            cv2.rectangle(canvas, (x1, y1), (x2, y2), color, -1)
            cv2.rectangle(canvas, (x1, y1), (x2, y2), border, 2)
            font_scale = 0.7 if len(label) <= 2 else 0.48
            text_size = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, font_scale, 2)[0]
            text_x = x1 + (key_width - text_size[0]) // 2
            text_y = y1 + (y2 - y1 + text_size[1]) // 2
            text_color = (12, 25, 35) if selected else (235, 240, 245)
            cv2.putText(canvas, label, (text_x, text_y), cv2.FONT_HERSHEY_SIMPLEX,
                        font_scale, text_color, 2, cv2.LINE_AA)


def draw_typed_text(canvas, typed_text):
    """Show the most recent text in a dedicated, readable output panel."""
    panel_top = 368
    panel_bottom = 460
    cv2.rectangle(canvas, (12, panel_top), (1088, panel_bottom), (25, 35, 45), -1)
    cv2.rectangle(canvas, (12, panel_top), (1088, panel_bottom), (100, 235, 150), 2)
    cv2.putText(canvas, "TYPED TEXT", (28, panel_top + 28), cv2.FONT_HERSHEY_SIMPLEX,
                0.55, (100, 235, 150), 2, cv2.LINE_AA)

    visible_text = typed_text.replace("\n", " | ")
    if not visible_text:
        visible_text = "Your typed text will appear here"
    visible_text = visible_text[-70:]
    cv2.putText(canvas, visible_text, (28, panel_top + 70), cv2.FONT_HERSHEY_SIMPLEX,
                0.9, (245, 250, 250), 2, cv2.LINE_AA)


def draw_eyebrow_overlay(frame, landmarks, measurements, neutral_level=None):
    """Draw brow landmarks and the eyelid-to-brow distance used for navigation."""
    height, width = frame.shape[:2]
    brow_groups = ((LEFT_BROW, LEFT_EYE, (0, 220, 255), "L brow"),
                   (RIGHT_BROW, RIGHT_EYE, (255, 120, 0), "R brow"))
    for brow_indices, eye, color, label in brow_groups:
        brow_x = sum(landmarks[index].x for index in brow_indices) / len(brow_indices)
        brow_y = sum(landmarks[index].y for index in brow_indices) / len(brow_indices)
        brow_point = int(brow_x * width), int(brow_y * height)
        eyelid = landmarks[eye["top"]]
        eyelid_point = int(eyelid.x * width), int(eyelid.y * height)
        cv2.line(frame, brow_point, eyelid_point, color, 3)
        cv2.circle(frame, brow_point, 9, color, -1)
        cv2.circle(frame, eyelid_point, 6, (255, 255, 255), -1)
        cv2.putText(frame, label, (brow_point[0] + 10, brow_point[1] - 8),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2, cv2.LINE_AA)

    level = measurements["level"]
    cv2.putText(frame, f"brow signal {level:.3f}", (12, height - 18),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2, cv2.LINE_AA)
    if neutral_level is not None:
        delta = level - neutral_level
        cv2.putText(frame, f"neutral {neutral_level:.3f}  delta {delta:+.3f}", (12, height - 44),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (80, 255, 80), 2, cv2.LINE_AA)


def activate_key(label, text):
    if label == "SPACE":
        return text + " "
    if label == "BACKSPACE":
        return text[:-1]
    if label == "ENTER":
        return text + "\n"
    return text + label


def move_keyboard_row(selected_row, direction):
    return max(0, min(selected_row + direction, len(KEYBOARD) - 1))


def main():
    face_mesh = mp.solutions.face_mesh.FaceMesh(
        max_num_faces=1, refine_landmarks=True,
        min_detection_confidence=0.6, min_tracking_confidence=0.6,
    )
    cap = cv2.VideoCapture(CAM_INDEX)
    if not cap.isOpened():
        sys.exit("Could not open webcam. Try a different CAM_INDEX.")
    log_file, log_writer = open_debug_log()

    selected_row = 0
    selected_col = 0
    typed_text = ""
    left_closed = right_closed = 0
    neutral_samples = []
    neutral_level = None
    last_action = 0.0
    status = "Keep eyebrows relaxed for calibration..."
    frame_number = 0
    left_open = right_open = None
    mouth_ratio = None
    mouth_open_started = None
    mouth_press_used = False
    next_mouth_duration = MOUTH_FIRST_PRESS_SECONDS
    brow_direction = None
    brow_move_started = None
    brow_move_used = False
    next_brow_duration = EYEBROW_FIRST_MOVE_SECONDS
    brow_armed = False
    brow_neutral_started = None
    neutral_hold_seconds = 0.0
    brow_neutral_samples = []
    smoothed_brow_level = None
    show_brow_overlay = True

    try:
        cv2.namedWindow(WINDOW, cv2.WINDOW_NORMAL)
        cv2.resizeWindow(WINDOW, 1100, 800)
        while True:
            frame_number += 1
            action = ""
            measurements = {}
            left_open = right_open = None
            mouth_ratio = None
            ret, frame = cap.read()
            if not ret:
                break
            frame = cv2.flip(frame, 1)
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            face_result = face_mesh.process(rgb)
            canvas = cv2.resize(frame, (1100, 800))
            if face_result.multi_face_landmarks:
                landmarks = face_result.multi_face_landmarks[0].landmark
                measurements = eyebrow_measurements(landmarks)
                level = measurements["level"]
                if show_brow_overlay:
                    draw_eyebrow_overlay(frame, landmarks, measurements, neutral_level)
                    canvas = cv2.resize(frame, (1100, 800))

                if neutral_level is None:
                    neutral_samples.append(level)
                    if len(neutral_samples) >= CALIBRATION_FRAMES:
                        neutral_level = sorted(neutral_samples)[len(neutral_samples) // 2]
                        smoothed_brow_level = level
                        brow_armed = True
                        status = "Ready - raise/lower eyebrows, wink to move, mouth to press"
                else:
                    smoothed_brow_level += EYEBROW_SMOOTHING * (level - smoothed_brow_level)
                    level = smoothed_brow_level
                    measurements["level"] = level
                    left_open = eye_openness(landmarks, LEFT_EYE)
                    right_open = eye_openness(landmarks, RIGHT_EYE)
                    mouth_ratio = mouth_openness(landmarks)
                    mouth_is_open = mouth_ratio >= MOUTH_OPEN_THRESHOLD
                    left_is_closed = left_open < EYE_CLOSED
                    right_is_closed = right_open < EYE_CLOSED
                    left_closed = left_closed + 1 if left_is_closed else 0
                    right_closed = right_closed + 1 if right_is_closed else 0
                    now = time.monotonic()

                    if mouth_is_open:
                        if mouth_open_started is None:
                            mouth_open_started = now
                        mouth_open_seconds = now - mouth_open_started
                        if (not mouth_press_used and
                                mouth_open_seconds >= next_mouth_duration and
                                now - last_action >= ACTION_COOLDOWN):
                            typed_text = activate_key(KEYBOARD[selected_row][selected_col], typed_text)
                            status = "Pressed " + KEYBOARD[selected_row][selected_col]
                            action = "mouth_hold_press"
                            last_action = now
                            mouth_press_used = True
                            next_mouth_duration = MOUTH_REPEAT_PRESS_SECONDS
                        elif not mouth_press_used:
                            status = f"Hold mouth open {max(0, next_mouth_duration - mouth_open_seconds):.1f}s"
                    else:
                        if mouth_open_started is not None and mouth_press_used:
                            status = "Mouth closed - open again and hold for 3.0s"
                        mouth_open_started = None
                        mouth_press_used = False

                    brow_delta = level - neutral_level
                    neutral_hold_seconds = 0.0
                    if not brow_armed:
                        brow_direction = None
                        brow_move_started = None
                        if abs(brow_delta) <= EYEBROW_RESET_ZONE:
                            if brow_neutral_started is None:
                                brow_neutral_started = now
                                brow_neutral_samples.clear()
                            brow_neutral_samples.append(level)
                            neutral_hold_seconds = now - brow_neutral_started
                            if neutral_hold_seconds >= EYEBROW_NEUTRAL_HOLD_SECONDS:
                                neutral_level = sum(brow_neutral_samples) / len(brow_neutral_samples)
                                brow_armed = True
                                brow_neutral_started = None
                                brow_move_used = False
                                brow_neutral_samples.clear()
                                status = "Neutral confirmed - eyebrows armed"
                            else:
                                status = (f"Hold eyebrows neutral "
                                          f"{neutral_hold_seconds:.1f}/{EYEBROW_NEUTRAL_HOLD_SECONDS:.1f}s")
                        else:
                            brow_neutral_started = None
                            brow_neutral_samples.clear()
                            status = "Relax eyebrows to neutral to rearm"
                    else:
                        if abs(brow_delta) <= EYEBROW_RESET_ZONE:
                            neutral_level += 0.005 * brow_delta
                            brow_delta = level - neutral_level
                            brow_direction = None
                            brow_move_started = None
                            brow_move_used = False
                        elif brow_delta > EYEBROW_DEADZONE:
                            if brow_direction != "up":
                                brow_direction = "up"
                                brow_move_started = now
                                brow_move_used = False
                            brow_seconds = now - brow_move_started
                        elif brow_delta < -EYEBROW_DEADZONE:
                            if brow_direction != "down":
                                brow_direction = "down"
                                brow_move_started = now
                                brow_move_used = False
                            brow_seconds = now - brow_move_started
                        else:
                            brow_direction = None
                            brow_move_started = None
                            brow_move_used = False

                    if (brow_direction and brow_move_started and not brow_move_used and
                            brow_seconds >= next_brow_duration and
                            now - last_action >= ACTION_COOLDOWN and not mouth_is_open):
                        if brow_direction == "up":
                            previous_row = selected_row
                            selected_row = move_keyboard_row(selected_row, -1)
                            selected_col = min(selected_col, len(KEYBOARD[selected_row]) - 1)
                            if selected_row == previous_row:
                                status = "Already at top row; relax eyebrows to rearm"
                                action = "eyebrow_raise_at_top"
                            else:
                                status = "Eyebrows raised: moved up; relax to rearm"
                                action = "eyebrow_raise"
                        else:
                            previous_row = selected_row
                            selected_row = move_keyboard_row(selected_row, 1)
                            selected_col = min(selected_col, len(KEYBOARD[selected_row]) - 1)
                            if selected_row == previous_row:
                                status = "Already at bottom row; relax eyebrows to rearm"
                                action = "eyebrow_lower_at_bottom"
                            else:
                                status = "Eyebrows lowered: moved down; relax to rearm"
                                action = "eyebrow_lower"
                        last_action = now
                        brow_move_used = True
                        brow_armed = False
                        brow_neutral_started = None
                        brow_neutral_samples.clear()
                        next_brow_duration = EYEBROW_REPEAT_MOVE_SECONDS

                    if now - last_action >= ACTION_COOLDOWN and not mouth_is_open:
                        if right_closed >= WINK_MIN_FRAMES:
                            selected_col = min(selected_col + 1, len(KEYBOARD[selected_row]) - 1)
                            status = "Right wink: moved right"
                            action = "right_wink"
                            last_action = now
                            right_closed = 0
                        elif left_closed >= WINK_MIN_FRAMES:
                            selected_col = max(selected_col - 1, 0)
                            status = "Left wink: moved left"
                            action = "left_wink"
                            last_action = now
                            left_closed = 0

                    if brow_direction and not brow_move_used and brow_armed:
                        remaining = max(0, next_brow_duration - (now - brow_move_started))
                        status = f"Hold eyebrows {brow_direction} {remaining:.1f}s"

            write_debug_log(
                log_file, log_writer, frame_number, measurements, neutral_level,
                selected_row, selected_col, action, status, left_open, right_open,
                mouth_ratio if mouth_ratio is not None else "", brow_armed,
                neutral_hold_seconds,
            )

            preview = cv2.resize(frame, (1100, 360))
            canvas[:360] = preview
            cv2.rectangle(canvas, (0, 0), (1099, 359), (0, 210, 255), 2)
            cv2.putText(canvas, status, (18, 32), cv2.FONT_HERSHEY_SIMPLEX,
                        0.65, (255, 255, 255), 2, cv2.LINE_AA)
            if measurements:
                delta = measurements["level"] - neutral_level if neutral_level is not None else 0.0
                debug_text = f"brow {measurements['level']:.3f}  neutral {neutral_level or 0:.3f}  delta {delta:+.3f}"
            else:
                debug_text = "face not detected"
            cv2.putText(canvas, debug_text, (18, 62), cv2.FONT_HERSHEY_SIMPLEX,
                        0.55, (0, 220, 255), 2, cv2.LINE_AA)
            if left_open is not None and right_open is not None:
                eye_text = f"eyes L {left_open:.2f} R {right_open:.2f}  closed frames L {left_closed} R {right_closed}"
                cv2.putText(canvas, eye_text, (18, 88), cv2.FONT_HERSHEY_SIMPLEX,
                            0.5, (0, 220, 255), 2, cv2.LINE_AA)
            if mouth_ratio is not None:
                mouth_time = time.monotonic() - mouth_open_started if mouth_open_started else 0.0
                mouth_text = f"mouth {mouth_ratio:.2f}  open time {mouth_time:.1f}s / next press {next_mouth_duration:.1f}s"
                cv2.putText(canvas, mouth_text, (18, 112), cv2.FONT_HERSHEY_SIMPLEX,
                            0.5, (0, 220, 255), 2, cv2.LINE_AA)
            draw_typed_text(canvas, typed_text)
            draw_keyboard(canvas, selected_row, selected_col)
            cv2.imshow(WINDOW, canvas)

            key = cv2.waitKey(1) & 0xFF
            if key == ord("q"):
                break
            if key == ord("k"):
                show_brow_overlay = not show_brow_overlay
            if key == ord("r"):
                neutral_level = None
                neutral_samples.clear()
                mouth_open_started = None
                mouth_press_used = False
                next_mouth_duration = MOUTH_FIRST_PRESS_SECONDS
                brow_direction = None
                brow_move_started = None
                brow_move_used = False
                next_brow_duration = EYEBROW_FIRST_MOVE_SECONDS
                brow_armed = False
                brow_neutral_started = None
                neutral_hold_seconds = 0.0
                brow_neutral_samples.clear()
                smoothed_brow_level = None
                status = "Keep eyebrows relaxed for calibration..."
    finally:
        cap.release()
        log_file.close()
        face_mesh.close()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
