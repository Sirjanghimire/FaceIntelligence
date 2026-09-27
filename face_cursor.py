"""
face_cursor.py — THE main program.

    head turn       -> moves the mouse cursor (joystick: turn = drift, face screen = stop)
    mouth open      -> left click   (hold 1 s -> right click)
    long blink      -> left click   (optional)
    dwell           -> left click   (optional)

Run:   python face_cursor.py
Then open  keyboard/index.html  in your browser and type with your face.

Keys in the debug window
    q  quit                    c  re-centre (face the screen, press c)
    p  pause / resume cursor   g  cycle joystick -> head -> gaze mode
    m  toggle mouth click      b  toggle blink click      d  toggle dwell click
    [  ]  lower / raise sensitivity
"""

import json
import os
import time

import cv2
import numpy as np
import pyautogui

from tracking import FaceTracker, OneEuroFilter

HERE = os.path.dirname(os.path.abspath(__file__))

pyautogui.FAILSAFE = False   # otherwise touching a screen corner throws an error
pyautogui.PAUSE = 0          # no artificial delay between pyautogui calls


# --------------------------------------------------------------------------- #
def load_config():
    with open(os.path.join(HERE, "config.json"), encoding="utf-8") as f:
        return json.load(f)


def load_calibration():
    path = os.path.join(HERE, "calibration.json")
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return np.array(data["coef_x"]), np.array(data["coef_y"])


# --------------------------------------------------------------------------- #
class ClickEngine:
    """Turns mouth / blink / dwell signals into clicks, with debouncing."""

    def __init__(self, cfg):
        self.cfg = cfg
        self.use_mouth = cfg["click_gesture"] == "mouth"
        self.use_blink = cfg["click_gesture"] == "blink"
        self.use_dwell = cfg["click_gesture"] == "dwell"
        self.last_click_t = 0.0

        self.mouth_open_since = None
        self.mouth_right_fired = False
        self.mouth_click_pos = None   # cursor frozen here while mouth open

        self.blink_since = None
        self.blink_pos = None

        self.dwell_anchor = None
        self.dwell_since = None
        self.dwell_armed = True

        self.flash = ""               # text shown in debug window

    # ----------------------------------------------------------------- #
    def _can_click(self, now):
        return now - self.last_click_t > self.cfg["click_cooldown_s"]

    def _click(self, now, button="left", pos=None):
        if not self._can_click(now):
            return
        if pos is not None:
            pyautogui.moveTo(*pos)
        pyautogui.click(button=button)
        self.last_click_t = now
        self.flash = f"{button.upper()} CLICK"

    # ----------------------------------------------------------------- #
    def update(self, s, cursor_pos, now):
        """s = signals dict (may be None), cursor_pos = where cursor is now.
        Returns a frozen cursor position if the cursor should not move."""
        frozen = None

        # ---------- mouth ------------------------------------------------
        if self.use_mouth and s is not None:
            if s["mar"] > self.cfg["mouth_open_threshold"]:
                if self.mouth_open_since is None:
                    self.mouth_open_since = now
                    self.mouth_click_pos = cursor_pos       # freeze here
                    self.mouth_right_fired = False
                held = now - self.mouth_open_since
                frozen = self.mouth_click_pos
                if held >= self.cfg["mouth_long_hold_s"] and not self.mouth_right_fired:
                    self._click(now, "right", self.mouth_click_pos)
                    self.mouth_right_fired = True
            else:
                if self.mouth_open_since is not None:
                    held = now - self.mouth_open_since
                    if self.cfg["mouth_min_hold_s"] <= held < self.cfg["mouth_long_hold_s"]:
                        self._click(now, "left", self.mouth_click_pos)
                    self.mouth_open_since = None
                    self.mouth_click_pos = None

        # ---------- blink ------------------------------------------------
        if self.use_blink and s is not None:
            if s["ear"] < self.cfg["blink_threshold"]:
                if self.blink_since is None:
                    self.blink_since = now
                    self.blink_pos = cursor_pos
                frozen = frozen or self.blink_pos
            else:
                if self.blink_since is not None:
                    held = now - self.blink_since
                    if self.cfg["blink_min_s"] <= held <= self.cfg["blink_max_s"]:
                        self._click(now, "left", self.blink_pos)
                    self.blink_since = None

        # ---------- dwell ------------------------------------------------
        if self.use_dwell:
            r = self.cfg["dwell_radius_px"]
            if self.dwell_anchor is None or \
               abs(cursor_pos[0] - self.dwell_anchor[0]) > r or \
               abs(cursor_pos[1] - self.dwell_anchor[1]) > r:
                self.dwell_anchor = cursor_pos
                self.dwell_since = now
                self.dwell_armed = True
            elif self.dwell_armed and now - self.dwell_since >= self.cfg["dwell_time_s"]:
                self._click(now, "left", self.dwell_anchor)
                self.dwell_armed = False        # must move away to re-arm

        return frozen

    def dwell_progress(self, now):
        if not self.use_dwell or self.dwell_since is None or not self.dwell_armed:
            return 0.0
        return min(1.0, (now - self.dwell_since) / self.cfg["dwell_time_s"])


# --------------------------------------------------------------------------- #
class CursorMapper:
    """Converts face signals into screen coordinates.

    Modes
      joystick  head turn = cursor VELOCITY. Turn a little -> cursor drifts slowly
                that way; face the screen -> cursor stops dead. Slow but very
                controllable. (default)
      head      head turn = cursor POSITION (faster, needs a steady head)
      gaze      eyes+head model from calibration.py
    """

    def __init__(self, cfg, screen_w, screen_h):
        self.cfg = cfg
        self.sw, self.sh = screen_w, screen_h
        self.mode = cfg["cursor_mode"]
        self.gain_x = cfg["head_gain_x"]
        self.gain_y = cfg["head_gain_y"]
        self.speed_x = cfg["joystick_speed_x"]
        self.speed_y = cfg["joystick_speed_y"]
        self.center = None                 # (yaw0, pitch0) — your neutral pose
        self.calib = load_calibration()
        if self.mode == "gaze" and self.calib is None:
            print("No calibration.json found -> run calibration.py first. Falling back to joystick mode.")
            self.mode = "joystick"

        # Stage 1: smooth the raw head angles (kills landmark jitter)
        self.f_yaw = OneEuroFilter(cfg["signal_min_cutoff"], cfg["signal_beta"])
        self.f_pitch = OneEuroFilter(cfg["signal_min_cutoff"], cfg["signal_beta"])
        # Stage 2: smooth the screen position (kills remaining wobble)
        self.fx = OneEuroFilter(cfg["smoothing_min_cutoff"], cfg["smoothing_beta"])
        self.fy = OneEuroFilter(cfg["smoothing_min_cutoff"], cfg["smoothing_beta"])

        self._center_samples = []
        self.pos = [screen_w / 2, screen_h / 2]     # joystick integrates into this
        self.last_t = None
        self.last_sent = None                       # last position actually sent

    def recenter(self):
        self.center = None
        self._center_samples = []
        for f in (self.f_yaw, self.f_pitch, self.fx, self.fy):
            f.reset()
        self.last_t = None

    def sync(self, cursor_pos):
        """Keep the joystick position in sync with the real cursor (e.g. after a click)."""
        self.pos = [float(cursor_pos[0]), float(cursor_pos[1])]

    @staticmethod
    def _deadzone(v, dz):
        if abs(v) < dz:
            return 0.0
        return v - dz if v > 0 else v + dz

    def map(self, s, now):
        yaw = self.f_yaw(s["yaw"], now)
        pitch = self.f_pitch(s["pitch"], now)

        # Collect ~1 s of frames to define "neutral" head pose
        if self.center is None:
            self._center_samples.append((yaw, pitch))
            if len(self._center_samples) < 25:
                return None
            arr = np.array(self._center_samples)
            self.center = tuple(np.median(arr, axis=0))
            self.last_t = now
            print(f"Centred. neutral yaw={self.center[0]:+.3f} pitch={self.center[1]:+.3f}")
            return None

        dt = min(max(now - (self.last_t or now), 0.0), 0.1)
        self.last_t = now
        dx = yaw - self.center[0]
        dy = pitch - self.center[1]

        if self.mode == "gaze" and self.calib is not None:
            feat = np.array([s["gaze_x"], s["gaze_y"], yaw, pitch, 1.0])
            x = float(feat @ self.calib[0])
            y = float(feat @ self.calib[1])

        elif self.mode == "head":
            dz = self.cfg["deadzone"]
            dx, dy = self._deadzone(dx, dz), self._deadzone(dy, dz)
            x = self.sw / 2 + dx * self.gain_x * self.sw
            y = self.sh / 2 + dy * self.gain_y * self.sh

        else:  # joystick
            dz = self.cfg["joystick_deadzone"]
            curve = self.cfg["joystick_curve"]
            dx, dy = self._deadzone(dx, dz), self._deadzone(dy, dz)
            # response curve: gentle near the centre, faster when you turn further
            vx = np.sign(dx) * (abs(dx) * 10) ** curve * self.speed_x * self.sw
            vy = np.sign(dy) * (abs(dy) * 10) ** curve * self.speed_y * self.sh
            self.pos[0] = float(np.clip(self.pos[0] + vx * dt, 0, self.sw - 1))
            self.pos[1] = float(np.clip(self.pos[1] + vy * dt, 0, self.sh - 1))
            x, y = self.pos

        x = self.fx(x, now)
        y = self.fy(y, now)
        target = (int(np.clip(x, 0, self.sw - 1)), int(np.clip(y, 0, self.sh - 1)))

        # Jitter lock: ignore sub-pixel wobble so a parked cursor stays parked
        lock = self.cfg["jitter_lock_px"]
        if self.last_sent is not None and \
           abs(target[0] - self.last_sent[0]) <= lock and abs(target[1] - self.last_sent[1]) <= lock:
            return self.last_sent
        self.last_sent = target
        return target


# --------------------------------------------------------------------------- #
def main():
    cfg = load_config()
    screen_w, screen_h = pyautogui.size()
    tracker = FaceTracker(cfg["camera_index"])
    mapper = CursorMapper(cfg, screen_w, screen_h)
    clicker = ClickEngine(cfg)
    paused = False
    lost_face_since = None

    print(__doc__)
    print(f"Screen {screen_w}x{screen_h}.  Mode: {mapper.mode}.  Face the screen and hold still for a second...")
    mapper.sync(pyautogui.position())

    while True:
        frame, s = tracker.read()
        if frame is None:
            print("Camera stopped.")
            break
        now = time.time()

        cursor_pos = pyautogui.position()
        target = None

        if s is None:
            lost_face_since = lost_face_since or now
        else:
            lost_face_since = None
            target = mapper.map(s, now)

        frozen = clicker.update(s, cursor_pos, now)

        if not paused and target is not None:
            if frozen is not None:
                pyautogui.moveTo(*frozen)
                mapper.sync(frozen)
            elif target != cursor_pos:
                pyautogui.moveTo(*target)

        # ---------------- debug window ------------------------------------
        if cfg["show_debug_window"]:
            tracker.draw_debug(frame, s)
            status = [
                f"mode {mapper.mode}   speed {mapper.speed_x:.2f}   gain {mapper.gain_x:.1f}   {'PAUSED' if paused else 'live'}",
                f"click: mouth {'ON' if clicker.use_mouth else 'off'}  blink {'ON' if clicker.use_blink else 'off'}  dwell {'ON' if clicker.use_dwell else 'off'}",
            ]
            if s:
                bar = int(min(s["mar"] / 0.6, 1.0) * 200)
                thr = int(min(cfg["mouth_open_threshold"] / 0.6, 1.0) * 200)
                cv2.rectangle(frame, (10, 100), (10 + bar, 118), (0, 165, 255), -1)
                cv2.line(frame, (10 + thr, 95), (10 + thr, 123), (255, 255, 255), 2)
                cv2.putText(frame, f"mouth {s['mar']:.2f}", (220, 116), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1)
                status.append(f"ear {s['ear']:.2f}  gaze {s['gaze_x']:.2f},{s['gaze_y']:.2f}")
            else:
                status.append("NO FACE - sit back in view of the camera")
            if clicker.flash and now - clicker.last_click_t < 0.5:
                cv2.putText(frame, clicker.flash, (10, 170), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 255, 0), 3)
            dp = clicker.dwell_progress(now)
            if dp > 0:
                cv2.ellipse(frame, (frame.shape[1] - 40, 40), (25, 25), -90, 0, int(360 * dp), (0, 255, 255), 4)
            for i, t in enumerate(status):
                cv2.putText(frame, t, (10, 25 + i * 24), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)

            sc = cfg["debug_window_scale"]
            small = cv2.resize(frame, None, fx=sc, fy=sc)
            cv2.imshow("Face Cursor  (q quit, c centre, p pause)", small)

        key = cv2.waitKey(1) & 0xFF
        if key == ord("q"):
            break
        elif key == ord("c"):
            mapper.recenter()
            print("Re-centring... hold your head still and look at the screen centre.")
        elif key == ord("p"):
            paused = not paused
        elif key == ord("g"):
            order = ["joystick", "head"] + (["gaze"] if mapper.calib is not None else [])
            mapper.mode = order[(order.index(mapper.mode) + 1) % len(order)] if mapper.mode in order else "joystick"
            mapper.sync(cursor_pos)
            mapper.recenter()
            print(f"Cursor mode: {mapper.mode}")
        elif key == ord("m"):
            clicker.use_mouth = not clicker.use_mouth
        elif key == ord("b"):
            clicker.use_blink = not clicker.use_blink
        elif key == ord("d"):
            clicker.use_dwell = not clicker.use_dwell
        elif key == ord("]"):
            mapper.gain_x *= 1.15; mapper.gain_y *= 1.15
            mapper.speed_x *= 1.15; mapper.speed_y *= 1.15
        elif key == ord("["):
            mapper.gain_x /= 1.15; mapper.gain_y /= 1.15
            mapper.speed_x /= 1.15; mapper.speed_y /= 1.15

    tracker.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
