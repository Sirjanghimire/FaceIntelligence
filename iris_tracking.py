"""Read only horizontal iris position and blink openness from a webcam."""
import math
import threading
import time

import cv2
import mediapipe as mp


def distance(a, b):
    return math.hypot(a.x - b.x, a.y - b.y)


class IrisTracker:
    def __init__(self, camera_index=0, width=640, height=480):
        self.camera = cv2.VideoCapture(camera_index)
        self.camera.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        self.camera.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        # Backends that support this discard queued old webcam frames.
        self.camera.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        self.camera.set(cv2.CAP_PROP_FPS, 30)
        if not self.camera.isOpened():
            self.camera.release()
            raise RuntimeError("Camera unavailable. Check camera_index in config.json.")
        self.mesh = mp.solutions.face_mesh.FaceMesh(
            max_num_faces=1, refine_landmarks=True,
            min_detection_confidence=.55, min_tracking_confidence=.55)

    @staticmethod
    def signals(points):
        # Iris center/rim and eye corners provide horizontal control. Eyelids
        # are used only for the optional deliberate-blink selection gesture.
        # No head, nose, cheeks, or vertical iris movement controls the cursor.
        def eye(iris, a, b, top, bottom):
            p, q = points[a], points[b]
            upper, lower = points[top], points[bottom]
            width = max(abs(q.x - p.x), 1e-5)
            iris_x = sum(points[i].x for i in iris) / len(iris)
            x = (iris_x - min(p.x, q.x)) / width
            ear = distance(upper, lower) / max(distance(p, q), 1e-5)
            return x, ear

        left = eye((468, 469, 470, 471, 472), 33, 133, 159, 145)
        right = eye((473, 474, 475, 476, 477), 362, 263, 386, 374)
        return {"eye_x": (left[0] + right[0]) / 2,
                "left_ear": left[1], "right_ear": right[1]}

    def read(self):
        ok, frame = self.camera.read()
        if not ok:
            return None, None
        frame = cv2.flip(frame, 1)
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        rgb.flags.writeable = False
        result = self.mesh.process(rgb)
        if not result.multi_face_landmarks:
            return frame, None
        points = result.multi_face_landmarks[0].landmark
        if len(points) < 478:
            return frame, None
        return frame, self.signals(points)

    def close(self):
        self.camera.release()
        self.mesh.close()


class LatestIrisTracker:
    """Run camera/landmarks outside Tk; expose only the newest finished sample.

    A slow camera never blocks drawing or pause controls. Old samples expire
    so a stalled camera cannot leave the cursor moving on stale gaze input.
    Calibration continues to use the synchronous IrisTracker above.
    """
    def __init__(self, camera_index=0, *, tracker_factory=None,
                 stale_after_s=.22, clock=time.monotonic):
        self._factory = tracker_factory or IrisTracker
        self._camera_index = camera_index
        self._clock = clock
        self._stale_after = stale_after_s
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._sample = None
        self._error = None
        self._starting = object()
        self._thread = threading.Thread(target=self._run, name="iris-camera", daemon=True)
        self._thread.start()

    def _run(self):
        tracker = None
        try:
            tracker = self._factory(self._camera_index)
            while not self._stop.is_set():
                started = self._clock()
                frame, signal = tracker.read()
                if frame is None:
                    raise RuntimeError("Camera stopped. Close other camera apps and restart run.bat.")
                # Include processing time in freshness, rather than treating a
                # very late landmark result as a newly captured image.
                with self._lock:
                    self._sample = frame, signal, started
        except Exception as exc:
            with self._lock:
                self._error = str(exc)
        finally:
            if tracker is not None:
                tracker.close()

    def read(self):
        with self._lock:
            sample, error = self._sample, self._error
        if error is not None:
            raise RuntimeError(error)
        if sample is None:
            return self._starting, None
        frame, signal, captured_at = sample
        return frame, signal if self._clock() - captured_at <= self._stale_after else None

    def close(self):
        self._stop.set()
        # Camera and MediaPipe are closed by their owning worker, not by Tk.
        self._thread.join(timeout=.5)
