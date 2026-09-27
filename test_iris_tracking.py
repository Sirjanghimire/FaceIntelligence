"""Camera-free checks that tracking cannot block the UI or reuse stale gaze."""
import importlib.util
from pathlib import Path
from queue import Queue
import sys
import unittest
from unittest.mock import MagicMock, patch


class LatestTrackingTests(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location(
            "tracking_under_test", Path(__file__).with_name("iris_tracking.py"))
        module = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {"cv2": MagicMock(), "mediapipe": MagicMock()}):
            spec.loader.exec_module(module)
        self.Latest = module.LatestIrisTracker

    def test_slow_camera_does_not_block_reads_and_only_latest_sample_is_used(self):
        requested, frames = Queue(), Queue()
        clock = [0.]
        camera = MagicMock()

        def read():
            requested.put(True)
            return frames.get(timeout=2)

        camera.read.side_effect = read
        tracker = self.Latest(tracker_factory=lambda index: camera, clock=lambda: clock[0])
        try:
            requested.get(timeout=1)
            # Worker is blocked waiting for a camera frame; UI reads still return.
            self.assertIsNone(tracker.read()[1])
            frames.put(("first", {"eye_x": .4}))
            requested.get(timeout=1)  # first result published before next read
            frames.put(("second", {"eye_x": .6}))
            requested.get(timeout=1)
            self.assertEqual(tracker.read(), ("second", {"eye_x": .6}))
            clock[0] = .23
            self.assertEqual(tracker.read(), ("second", None))
        finally:
            frames.put((None, None))
            tracker.close()
        camera.close.assert_called_once()

    def test_camera_startup_failure_reaches_the_ui(self):
        factory = MagicMock(side_effect=RuntimeError("Camera unavailable"))
        tracker = self.Latest(tracker_factory=factory)
        tracker._thread.join(timeout=1)
        try:
            with self.assertRaisesRegex(RuntimeError, "Camera unavailable"):
                tracker.read()
        finally:
            tracker.close()


if __name__ == "__main__":
    unittest.main()
