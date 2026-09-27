"""
tracking.py — shared face-tracking layer.

Every other script imports FaceTracker from here so that the maths for
head pose, gaze ratio, mouth-open and blink lives in ONE place.

Signals produced per frame (all normalised, camera-resolution independent):
    yaw      head turned left/right   (negative = left,  positive = right)
    pitch    head tilted up/down      (negative = up,    positive = down)
    gaze_x   iris position inside eye (0 = far left,  1 = far right)
    gaze_y   iris position inside eye (0 = top,       1 = bottom)
    mar      mouth aspect ratio       (~0.05 closed,   >0.35 open)
    ear      eye aspect ratio         (~0.30 open,     <0.18 closed)
"""

import math
import cv2
import mediapipe as mp

mp_face_mesh = mp.solutions.face_mesh

# ---- MediaPipe FaceMesh landmark indices we rely on -------------------------
NOSE_TIP = 1
FOREHEAD = 10
CHIN = 152
LEFT_CHEEK = 234      # image-left side of the face (after flip = user's left)
RIGHT_CHEEK = 454

# Clusters of landmarks that are averaged for a steadier head-pose signal
NOSE_CLUSTER = (1, 4, 5, 195, 197)
LEFT_SIDE = (234, 93, 132)
RIGHT_SIDE = (454, 323, 361)
TOP_SIDE = (10, 109, 338)
BOTTOM_SIDE = (152, 148, 377)

# Eyes (iris landmarks 468-477 exist only with refine_landmarks=True)
L_IRIS = 468
R_IRIS = 473
L_EYE_OUTER, L_EYE_INNER = 33, 133
R_EYE_INNER, R_EYE_OUTER = 362, 263
L_EYE_TOP, L_EYE_BOTTOM = 159, 145
R_EYE_TOP, R_EYE_BOTTOM = 386, 374

# Mouth
LIP_TOP_INNER = 13
LIP_BOTTOM_INNER = 14
MOUTH_LEFT = 61
MOUTH_RIGHT = 291

# Eyebrows (for later: eyebrow-raise gesture)
L_BROW = 105
R_BROW = 334


def _dist(a, b):
    return math.hypot(a.x - b.x, a.y - b.y)


class FaceTracker:
    """Wraps webcam + FaceMesh and returns a dict of clean signals per frame."""

    def __init__(self, camera_index=0, width=640, height=480):
        self.camera = cv2.VideoCapture(camera_index)
        self.camera.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        self.camera.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        self.face_mesh = mp_face_mesh.FaceMesh(
            max_num_faces=1,
            refine_landmarks=True,          # needed for iris landmarks
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5,
        )
        self.last_landmarks = None

    # ------------------------------------------------------------------ #
    def read(self):
        """Returns (frame, signals) — signals is None when no face is found."""
        ok, frame = self.camera.read()
        if not ok:
            return None, None

        frame = cv2.flip(frame, 1)                       # mirror = natural feel
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        rgb.flags.writeable = False
        results = self.face_mesh.process(rgb)

        if not results.multi_face_landmarks:
            self.last_landmarks = None
            return frame, None

        lm = results.multi_face_landmarks[0].landmark
        self.last_landmarks = lm
        return frame, self._signals(lm)

    # ------------------------------------------------------------------ #
    @staticmethod
    def _signals(lm):
        # --- head pose (ratios, so distance to camera barely matters) ---
        # Average several landmarks instead of trusting one point: each
        # landmark jitters a little, the mean of five jitters much less.
        nose_x = sum(lm[i].x for i in NOSE_CLUSTER) / len(NOSE_CLUSTER)
        nose_y = sum(lm[i].y for i in NOSE_CLUSTER) / len(NOSE_CLUSTER)
        left_x = sum(lm[i].x for i in LEFT_SIDE) / len(LEFT_SIDE)
        right_x = sum(lm[i].x for i in RIGHT_SIDE) / len(RIGHT_SIDE)
        top_y = sum(lm[i].y for i in TOP_SIDE) / len(TOP_SIDE)
        bot_y = sum(lm[i].y for i in BOTTOM_SIDE) / len(BOTTOM_SIDE)

        face_w = right_x - left_x
        face_h = bot_y - top_y
        face_cx = (right_x + left_x) / 2
        face_cy = (bot_y + top_y) / 2
        yaw = (nose_x - face_cx) / max(face_w, 1e-6)
        pitch = (nose_y - face_cy) / max(face_h, 1e-6)

        # --- gaze: iris position inside each eye box, averaged ---------
        def iris_ratio(iris, inner, outer, top, bottom):
            xmin, xmax = sorted([lm[inner].x, lm[outer].x])
            ymin, ymax = sorted([lm[top].y, lm[bottom].y])
            gx = (lm[iris].x - xmin) / max(xmax - xmin, 1e-6)
            gy = (lm[iris].y - ymin) / max(ymax - ymin, 1e-6)
            return gx, gy

        lgx, lgy = iris_ratio(L_IRIS, L_EYE_INNER, L_EYE_OUTER, L_EYE_TOP, L_EYE_BOTTOM)
        rgx, rgy = iris_ratio(R_IRIS, R_EYE_INNER, R_EYE_OUTER, R_EYE_TOP, R_EYE_BOTTOM)
        gaze_x = (lgx + rgx) / 2
        gaze_y = (lgy + rgy) / 2

        # --- mouth aspect ratio ------------------------------------------
        mar = _dist(lm[LIP_TOP_INNER], lm[LIP_BOTTOM_INNER]) / max(
            _dist(lm[MOUTH_LEFT], lm[MOUTH_RIGHT]), 1e-6)

        # --- eye aspect ratio (blink) -------------------------------------
        l_ear = _dist(lm[L_EYE_TOP], lm[L_EYE_BOTTOM]) / max(_dist(lm[L_EYE_OUTER], lm[L_EYE_INNER]), 1e-6)
        r_ear = _dist(lm[R_EYE_TOP], lm[R_EYE_BOTTOM]) / max(_dist(lm[R_EYE_OUTER], lm[R_EYE_INNER]), 1e-6)
        ear = (l_ear + r_ear) / 2

        # --- eyebrow height (for a future "raise brows" gesture) ----------
        brow = ((lm[L_EYE_TOP].y - lm[L_BROW].y) + (lm[R_EYE_TOP].y - lm[R_BROW].y)) / 2 / max(face_h, 1e-6)

        return {
            "yaw": yaw, "pitch": pitch,
            "gaze_x": gaze_x, "gaze_y": gaze_y,
            "mar": mar, "ear": ear, "brow": brow,
            "nose": (lm[NOSE_TIP].x, lm[NOSE_TIP].y),
        }

    # ------------------------------------------------------------------ #
    def draw_debug(self, frame, signals):
        """Draws the landmarks we actually use so you can see what the code sees."""
        if self.last_landmarks is None:
            cv2.putText(frame, "NO FACE", (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)
            return frame
        h, w, _ = frame.shape
        lm = self.last_landmarks

        def px(i):
            return int(lm[i].x * w), int(lm[i].y * h)

        for i in (L_IRIS, R_IRIS):
            cv2.circle(frame, px(i), 4, (255, 200, 0), -1)
        for i in (L_EYE_OUTER, L_EYE_INNER, R_EYE_INNER, R_EYE_OUTER,
                  L_EYE_TOP, L_EYE_BOTTOM, R_EYE_TOP, R_EYE_BOTTOM):
            cv2.circle(frame, px(i), 2, (0, 255, 0), -1)
        for i in (LIP_TOP_INNER, LIP_BOTTOM_INNER, MOUTH_LEFT, MOUTH_RIGHT):
            cv2.circle(frame, px(i), 3, (0, 165, 255), -1)
        cv2.circle(frame, px(NOSE_TIP), 5, (255, 0, 255), -1)
        return frame

    def release(self):
        self.camera.release()
        self.face_mesh.close()


class OneEuroFilter:
    """
    Smooths a signal with very little lag on fast moves and strong smoothing
    on slow moves — exactly what a head/eye cursor needs.
    (Casiez et al. 2012)
    """

    def __init__(self, min_cutoff=1.0, beta=0.02, d_cutoff=1.0):
        self.min_cutoff, self.beta, self.d_cutoff = min_cutoff, beta, d_cutoff
        self.x_prev = self.dx_prev = self.t_prev = None

    @staticmethod
    def _alpha(cutoff, dt):
        tau = 1.0 / (2 * math.pi * cutoff)
        return 1.0 / (1.0 + tau / dt)

    def __call__(self, x, t):
        if self.t_prev is None:
            self.x_prev, self.dx_prev, self.t_prev = x, 0.0, t
            return x
        dt = max(t - self.t_prev, 1e-6)
        dx = (x - self.x_prev) / dt
        a_d = self._alpha(self.d_cutoff, dt)
        dx_hat = a_d * dx + (1 - a_d) * self.dx_prev
        cutoff = self.min_cutoff + self.beta * abs(dx_hat)
        a = self._alpha(cutoff, dt)
        x_hat = a * x + (1 - a) * self.x_prev
        self.x_prev, self.dx_prev, self.t_prev = x_hat, dx_hat, t
        return x_hat

    def reset(self):
        self.x_prev = self.dx_prev = self.t_prev = None
