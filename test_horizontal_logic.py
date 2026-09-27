"""Headless checks of horizontal iris movement, selections and typing layout."""
import json
import importlib
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from horizontal_logic import (DoubleBlink, Dwell, FocusStepper, HorizontalDriver,
                              LongBlink, TripleBlink, blink_thresholds,
                              calibrate_horizontal, delete_last_word,
                              delete_visible_character, keyboard_tiles,
                              load_calibration, predict_words)


CFG = json.loads((Path(__file__).parent / "config.json").read_text(encoding="utf-8"))
OPEN = {"left_ear": .25, "right_ear": .26}
CLOSED = {"left_ear": .07, "right_ear": .08}


def _fake_control(ui, cfg=CFG, cal=None, **extra):
    """Return an IrisControl instance with just enough attributes for tests."""
    control = ui.IrisControl.__new__(ui.IrisControl)
    control.cfg = cfg
    control.cal = cal if cal is not None else calibrate_horizontal(
        {"center": .5, "left": .42, "right": .59})
    control.cal["closed_thresholds"] = [.13, .14]
    control.selection = "blink"
    control.mode = "menu"
    control.menu_page = "home"
    control.key_page = "main"
    control.group = ""
    control.text = ""
    control.learned = []
    control.deletion_undo = None
    control.capitalize_next = False
    control.precision = False
    control.paused = False
    control.pause_ready = False
    control.pause_side_since = None
    control.pause_center_since = None
    control.pause_progress = 0.
    control.safe = False
    control.face_visible = True
    control.dwell_progress = 0.
    control.running = True
    control.sw = 1000
    control.sh = 600
    control.stage = "idle"
    control.plan = None
    control.suggestions = []
    control.result = ""
    control.review_page = 0
    control.contact_page = 0
    control.selected_contact = None
    control.selected_topic = ""
    control.pending_job = None
    control.mouse = (500, 300)
    control.last_mouse_sent = (500, 300)
    control.blink = LongBlink(control.cal, cfg)
    control.double_blink = DoubleBlink(control.cal, cfg)
    control.triple_blink = TripleBlink(control.cal, cfg)
    control.menu_dwell = Dwell(cfg)
    control.cursor_dwell = Dwell({**cfg, "dwell_time_s": 2.2})
    control.nav = FocusStepper(control.cal, control.sw, cfg, 7)
    control.pointer = HorizontalDriver(control.cal, control.sw, cfg["speed_x"], cfg)
    control._gemini_lock = threading.Lock()
    control._gemini_pending = None
    control._gemini_external = None
    control._gemini_last_fragment = None
    control._gemini_last_started = 0.
    control.assistant = SimpleNamespace(contacts=[])
    control.executor = MagicMock()
    control.root = MagicMock()
    control.bar = MagicMock()
    control.draw = MagicMock()
    control.message = MagicMock()
    control.tracker = MagicMock()
    control.tracker.read.return_value = (object(), {**OPEN, "eye_x": .5})
    control.activate_key = MagicMock()
    for key, value in extra.items():
        setattr(control, key, value)
    return control


class HorizontalLogicTests(unittest.TestCase):
    def setUp(self):
        self.cal = calibrate_horizontal({"center": .5, "left": .42, "right": .59})
        self.cal["closed_thresholds"] = [.13, .14]

    # ---- calibration ----

    def test_only_horizontal_signal_is_required(self):
        self.assertEqual(self.cal["model"], "horizontal-iris-v1")
        self.assertEqual(set(self.cal["span"]), {"left", "right"})
        with self.assertRaisesRegex(ValueError, "Horizontal iris signal"):
            calibrate_horizontal({"center": .5, "left": .499, "right": .501})
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "calibration.json"
            path.write_text(json.dumps({"model": "relative-iris-v2"}))
            with self.assertRaisesRegex(ValueError, "horizontal-only"):
                load_calibration(path)

    def test_landmarks_follow_irises_not_head_translation_or_eye_height(self):
        with patch.dict(sys.modules, {"cv2": MagicMock(), "mediapipe": MagicMock()}):
            tracker = importlib.import_module("iris_tracking")

        def sample(iris_dx=0, iris_dy=0, translation=0):
            points = [SimpleNamespace(x=translation, y=0.) for _ in range(478)]
            for a, b, iris_ids, upper, lower, center in (
                (33, 133, range(468, 473), 159, 145, .3),
                (362, 263, range(473, 478), 386, 374, .7),
            ):
                points[a] = SimpleNamespace(x=center - .1 + translation, y=.3)
                points[b] = SimpleNamespace(x=center + .1 + translation, y=.3)
                points[upper] = SimpleNamespace(x=center + translation, y=.28)
                points[lower] = SimpleNamespace(x=center + translation, y=.34)
                for index in iris_ids:
                    points[index] = SimpleNamespace(x=center + iris_dx + translation,
                                                    y=.31 + iris_dy)
            return tracker.IrisTracker.signals(points)

        baseline = sample()
        self.assertEqual(set(baseline), {"eye_x", "left_ear", "right_ear"})
        self.assertAlmostEqual(baseline["eye_x"], sample(translation=.2)["eye_x"])
        self.assertAlmostEqual(baseline["eye_x"], sample(iris_dy=.08)["eye_x"])
        self.assertGreater(sample(iris_dx=.025)["eye_x"], baseline["eye_x"] + .1)

    def test_mirrored_horizontal_calibration(self):
        cal = calibrate_horizontal({"center": .5, "left": .58, "right": .41})
        self.assertEqual(cal["sign"], -1)
        d = HorizontalDriver(cal, 1000, .7, CFG)
        for t in (0, .05, .10, .15):
            pos = d.move(.43, t)
        self.assertGreater(pos, 500)

    # ---- cursor movement ----

    def test_right_iris_moves_down_when_axis_is_vertical(self):
        y = HorizontalDriver(self.cal, 600, CFG["speed_y"], CFG)
        y.sync(300)
        for t in (0, .05, .10, .15, .2):
            down = y.move(.57, t)
        self.assertGreater(down, 300)
        self.assertEqual(y.move(.50, .25), down)
        for t in (.30, .35, .40, .45, .50, .55):
            up = y.move(.43, t)
        self.assertLess(up, down)
        self.assertEqual(y.move(None, .60), up)

    def test_cursor_accelerates_gently_and_center_stops_without_drift(self):
        cursor = HorizontalDriver(self.cal, 1000, CFG["speed_x"], CFG)
        cursor.sync(500)
        for t in (0, .05, .10, .15, .20):
            position = cursor.move(.57, t)
        self.assertGreater(position, 500)
        self.assertGreater(position, 520)
        self.assertLess(position, 575)
        self.assertEqual(cursor.move(.5, .25), position)
        self.assertEqual(cursor.move(.5, .3), position)
        fine = HorizontalDriver(self.cal, 1000,
                                CFG["speed_x"] * CFG["fine_speed_factor"], CFG)
        fine.sync(500)
        for t in (0, .05, .10, .15, .20):
            fine_position = fine.move(.57, t)
        self.assertGreater(fine_position, 500)
        self.assertLess(fine_position, position)

    def test_live_cursor_mode_moves_y_and_menu_freezes_desktop_mouse(self):
        fake_mouse = MagicMock()
        fake_mouse.position.return_value = (500, 300)
        fake_mouse.FailSafeException = RuntimeError

        def moved(x, y):
            fake_mouse.position.return_value = (x, y)
        fake_mouse.moveTo.side_effect = moved
        with patch.dict(sys.modules, {"pyautogui": fake_mouse,
                                      "iris_tracking": MagicMock()}):
            ui = importlib.import_module("iris_control")
        self.addCleanup(patch.stopall)
        patch.object(ui, "pyautogui", fake_mouse).start()
        control = _fake_control(ui, mode="cursor_y")
        control.tracker.read.return_value = (object(), {**OPEN, "eye_x": .57})
        control.pointer = HorizontalDriver(self.cal, 600, CFG["speed_y"], CFG)
        control.pointer.sync(300)
        with patch.object(ui.time, "monotonic", side_effect=[0, .05, .1, .15, .2]):
            for _ in range(5):
                control.tick()
        self.assertGreater(control.mouse[1], 300)
        self.assertEqual(control.mouse[0], 500)
        fake_mouse.moveTo.reset_mock()
        control.mode = "menu"
        control.menu_page = "home"
        control.nav = FocusStepper(self.cal, 1000, CFG, 7)
        control.nav.reset(7, index=3)
        control.tracker.read.return_value = (object(), {**OPEN, "eye_x": .57})
        with patch.object(ui.time, "monotonic", side_effect=[.25 + i*.05 for i in range(8)]):
            for _ in range(8):
                control.tick()
        fake_mouse.moveTo.assert_not_called()

    # ---- navigation stepper (uses new nav_hold_s=0.18, nav_settle_s=0.12) ----

    def test_quick_glance_then_hold_repeats_and_center_stops(self):
        nav = FocusStepper(self.cal, 1000, CFG, 7)
        self.assertEqual(nav.index, 3)
        nav.update(.5, 0, 7)
        nav.update(.5, .12, 7)              # arm center (nav_release_s=0.10)
        nav.update(.57, .20, 7)
        nav.update(.57, .40, 7)             # hold past nav_hold_s=0.18
        self.assertEqual(nav.index, 4)
        # settle_until blocked; wait past nav_settle_s + repeat_delay
        nav.update(.57, .50, 7)
        nav.update(.57, 1.20, 7)
        self.assertEqual(nav.index, 5)

    def test_short_eye_noise_and_blinks_do_not_move_focus(self):
        nav = FocusStepper(self.cal, 1000, CFG, 7)
        nav.update(.5, 0, 7)
        nav.update(.5, .12, 7)
        nav.update(.57, .15, 7)
        nav.update(.5, .25, 7)
        nav.update(.57, .28, 7)
        nav.update(.57, .40, 7)             # 0.12 < nav_hold_s 0.18 → no step
        self.assertEqual(nav.index, 3)
        nav.pause()
        nav.update(.57, .6, 7)
        nav.update(.57, .9, 7)
        self.assertEqual(nav.index, 3)
        nav.reset(2, index=0)
        self.assertEqual(nav.index, 0)

    def test_natural_blink_does_not_require_recentering_to_resume(self):
        nav = FocusStepper(self.cal, 1000, CFG, 10)
        nav.update(.5, 0, 10)
        nav.update(.5, .12, 10)
        nav.update(.57, .20, 10)
        nav.update(.57, .40, 10)
        self.assertEqual(nav.index, 6)
        nav.freeze()
        self.assertTrue(nav.armed)
        nav.update(.57, .55, 10)
        nav.update(.57, .80, 10)
        self.assertEqual(nav.index, 7)
        nav.update(None, .90, 10)
        nav.update(.57, 1.1, 10)
        nav.update(.57, 1.4, 10)
        self.assertEqual(nav.index, 7)

    def test_small_side_glance_responds_within_a_tenth_of_a_second(self):
        nav = FocusStepper(self.cal, 1000, CFG, 10)
        nav.update(.5, 0, 10)
        nav.update(.5, .12, 10)
        small_glance = .5 + self.cal["span"]["right"] * .35
        nav.update(small_glance, .20, 10)
        nav.update(small_glance, .42, 10)   # 0.22 > nav_hold_s 0.18 → step
        self.assertEqual(nav.index, 6)
        nav.update(.5, .50, 10)
        nav.update(.5, 1.0, 10)
        self.assertEqual(nav.index, 6)

    # ---- blink detectors ----

    def test_blink_selects_only_on_deliberate_release(self):
        b = LongBlink(self.cal, CFG)
        b.update(OPEN, 0.)
        b.update(OPEN, .20)
        self.assertEqual(b.update(CLOSED, .30), (True, False, False))
        self.assertEqual(b.update(OPEN, .43), (False, False, False))
        b.update(OPEN, .65)
        b.update(CLOSED, .75)
        self.assertEqual(b.update(OPEN, 1.32), (False, True, False))
        b.update(None, 1.45)
        self.assertEqual(b.update(CLOSED, 1.50), (True, False, False))
        b.update(OPEN, 2.)
        b.update(OPEN, 2.2)
        b.update(CLOSED, 2.3)
        self.assertEqual(b.update(OPEN, 4.), (False, False, True))

    def test_double_short_blink_deletes_once_without_selecting(self):
        double = DoubleBlink(self.cal, CFG)
        single = LongBlink(self.cal, CFG)
        events = []
        for t, signal in ((0, OPEN), (.2, OPEN), (.30, CLOSED), (.36, CLOSED),
                          (.43, OPEN), (.51, OPEN), (.59, CLOSED), (.66, CLOSED),
                          (.73, OPEN), (.80, OPEN), (.95, OPEN)):
            if double.update(signal, t):
                events.append(t)
            self.assertEqual(single.update(signal, t)[1:], (False, False))
        self.assertEqual(events, [.73])

    def test_double_blink_ignores_single_long_wink_and_missing_tracking(self):
        cases = (
            ((0, OPEN), (.2, OPEN), (.3, CLOSED), (.43, OPEN), (1., OPEN)),
            ((0, OPEN), (.2, OPEN), (.3, CLOSED), (.43, OPEN), (.65, OPEN),
             (.7, CLOSED), (1.3, OPEN)),
            ((0, OPEN), (.2, OPEN), (.3, CLOSED), (.43, OPEN), (.51, OPEN),
             (.59, CLOSED), (.65, None), (.73, OPEN)),
            ((0, CLOSED), (.15, OPEN), (.3, OPEN), (.4, CLOSED), (.53, OPEN)),
            ((0, OPEN), (.2, OPEN), (.3, {**OPEN, "left_ear": .07}), (.43, OPEN),
             (.6, {**OPEN, "left_ear": .07}), (.73, OPEN)),
        )
        for sequence in cases:
            detector = DoubleBlink(self.cal, CFG)
            with self.subTest(sequence=sequence):
                self.assertFalse(any(detector.update(signal, t) for t, signal in sequence))

    def test_triple_blink_fires_once_on_third_reopening(self):
        triple = TripleBlink(self.cal, CFG)
        events = []
        for t, signal in ((0, OPEN), (.15, OPEN),
                          (.25, CLOSED), (.31, CLOSED), (.38, OPEN),
                          (.48, OPEN),
                          (.56, CLOSED), (.62, CLOSED), (.69, OPEN),
                          (.78, OPEN),
                          (.86, CLOSED), (.92, CLOSED), (1.0, OPEN),
                          (1.1, OPEN)):
            if triple.update(signal, t):
                events.append(t)
        self.assertEqual(events, [1.0])

    def test_blink_calibration_keeps_sideways_look_open(self):
        thresholds, reliable = blink_thresholds([.16, .17], [.07, .08], .17)
        self.assertTrue(reliable)
        self.assertLess(thresholds[0], .16)
        _, reliable = blink_thresholds([.08, .08], [.07, .07], .17)
        self.assertFalse(reliable)

    # ---- pause / dwell ----

    def test_global_pause_freezes_pointer_and_short_blink_resumes(self):
        fake_mouse = MagicMock()
        fake_mouse.position.return_value = (500, 300)
        fake_mouse.FailSafeException = RuntimeError
        with patch.dict(sys.modules, {"pyautogui": fake_mouse,
                                      "iris_tracking": MagicMock()}):
            ui = importlib.import_module("iris_control")
        self.addCleanup(patch.stopall)
        patch.object(ui, "pyautogui", fake_mouse).start()
        control = _fake_control(ui, mode="cursor_x")
        control.blink = MagicMock()
        control.blink.update.return_value = (False, False, True)
        with patch.object(ui.time, "monotonic", return_value=0.):
            control.tick()
        self.assertTrue(control.paused)
        control.blink.update.return_value = (False, False, False)
        with patch.object(ui.time, "monotonic", return_value=.5):
            control.tick()
        fake_mouse.moveTo.assert_not_called()
        control.blink.update.return_value = (False, True, False)
        with patch.object(ui.time, "monotonic", return_value=1.):
            control.tick()
        self.assertFalse(control.paused)

    def test_dwell_pause_needs_side_glance_then_center_hold(self):
        with patch.dict(sys.modules, {"pyautogui": MagicMock(),
                                      "iris_tracking": MagicMock()}):
            ui = importlib.import_module("iris_control")
        control = _fake_control(ui, mode="menu")
        control.selection = "dwell"
        control.set_paused(True)
        control.update_pause_dwell(.5, .1)
        control.update_pause_dwell(.5, 2.)
        self.assertTrue(control.paused)
        control.update_pause_dwell(.57, 2.1)
        control.update_pause_dwell(.57, 2.3)
        control.update_pause_dwell(.5, 2.4)
        control.update_pause_dwell(.5, 3.3)
        self.assertFalse(control.paused)

    def test_dwell_requires_moving_focus_to_rearm(self):
        d = Dwell(CFG)
        self.assertEqual(d.update(300, 0), (False, 0.))
        self.assertTrue(d.update(303, 1.3)[0])
        self.assertFalse(d.update(300, 2)[0])
        self.assertFalse(d.update(500, 2.1)[0])
        self.assertTrue(d.update(500, 3.4)[0])

    # ---- double-blink in typing ----

    def test_double_blink_in_typing_deletes_word_and_protects_recipient(self):
        with patch.dict(sys.modules, {"pyautogui": MagicMock(), "iris_tracking": MagicMock()}):
            ui = importlib.import_module("iris_control")
        control = _fake_control(ui, mode="keyboard", key_page="main")
        control.selected_contact = {"name": "Sam", "email": "sam@real.test"}
        prefix = "email sam@real.test that "
        control.text = prefix + "please call tomorrow "
        with patch.object(ui.pyautogui, "position", return_value=(500, 300)):
            for t, signal in ((0, OPEN), (.2, OPEN), (.3, CLOSED), (.43, OPEN),
                              (.51, OPEN), (.59, CLOSED), (.73, OPEN)):
                control.tracker.read.return_value = (object(), {**signal, "eye_x": .5})
                with patch.object(ui.time, "monotonic", return_value=t):
                    control.tick()
        self.assertEqual(control.text, prefix + "please call ")
        control.activate_key.assert_not_called()
        ui.IrisControl.activate_key(control, "undo_delete")
        self.assertEqual(control.text, prefix + "please call tomorrow ")
        for _ in range(6):
            control.delete_text(whole_word=True)
        self.assertEqual(control.text, prefix)
        control.delete_text()
        self.assertEqual(control.text, prefix)

    # ---- keyboard layout (current single-page design) ----

    def test_every_letter_has_a_top_row_target(self):
        main = keyboard_tiles("main", "", "")
        groups = [action[6:] for _, action in main if action.startswith("group:")]
        self.assertEqual("".join(groups), "ABCDEFGHIJKLMNOPQRSTUVWXYZ")
        for group in groups:
            letters = keyboard_tiles("letters", group, "")
            self.assertLessEqual(len(letters), 7)
            self.assertIn(("BACK", "page:main"), letters)
        self.assertEqual(predict_words("ema")[0], "email")
        symbols = keyboard_tiles("symbols", "", "")
        self.assertIn(("123", "page:digits1"), symbols)
        numbers = keyboard_tiles("digits1", "", "") + keyboard_tiles("digits2", "", "")
        self.assertEqual("".join(label for label, action in numbers
                                 if action.startswith("letter:")), "1234567890")

    def test_quick_words_are_visible_configurable_and_type_in_one_selection(self):
        main = keyboard_tiles("main", "", "")
        self.assertEqual(main[-5:], [("SPACE", "space"), ("DEL", "delete"),
                                     ("RUN", "run"), ("QUICK", "page:quick"),
                                     ("BACK", "page:main")])
        quick = keyboard_tiles("quick", "", "", quick_words=CFG["quick_words"])
        self.assertEqual([label for label, _ in quick],
                         ["EMAIL", "YOUTUBE", "CALENDAR", "GOOGLE", "SEARCH", "MESSAGE",
                          "DEL", "RUN", "BACK"])
        self.assertIn("calendar", predict_words("cal"))
        self.assertEqual(predict_words("open ")[:3], ["email", "YouTube", "calendar"])
        self.assertEqual(keyboard_tiles("quick", "", "", quick_words=["music", "maps"]),
                         [("MUSIC", "word:music"), ("MAPS", "word:maps"),
                          ("DEL", "delete"), ("RUN", "run"),
                          ("BACK", "page:main")])

        with patch.dict(sys.modules, {"pyautogui": MagicMock(),
                                      "iris_tracking": MagicMock()}):
            ui = importlib.import_module("iris_control")
        control = _fake_control(ui, mode="keyboard", key_page="quick", text="ema")

        control.nav = FocusStepper(self.cal, 1000, CFG, len(quick))
        ui.IrisControl.activate_key(control, "word:email")
        self.assertEqual(control.text, "email ")
        self.assertEqual(control.key_page, "quick")
        ui.IrisControl.activate_key(control, "word:YouTube")
        self.assertEqual(control.text, "email YouTube ")
        ui.IrisControl.activate_key(control, "page:main")
        self.assertEqual((control.key_page, control.nav.count, control.nav.index),
                         ("main", 14, 7))

    def test_delete_is_visible_and_removes_text_after_a_predicted_word(self):
        self.assertIn(("DEL", "delete"), keyboard_tiles("main", "", "email "))
        self.assertEqual(delete_visible_character("email "), "emai")
        self.assertEqual(delete_visible_character("email Priya  "), "email Priy")
        self.assertEqual(delete_visible_character(""), "")
        self.assertEqual(delete_last_word("email Priya that "), "email Priya ")
        self.assertEqual(delete_last_word("email "), "")

        with patch.dict(sys.modules, {"pyautogui": MagicMock(),
                                      "iris_tracking": MagicMock()}):
            ui = importlib.import_module("iris_control")
        control = _fake_control(ui, mode="keyboard", key_page="quick")
        ui.IrisControl.activate_key(control, "word:email")
        self.assertEqual(control.key_page, "contacts")
        ui.IrisControl.activate_key(control, "contact_manual")
        ui.IrisControl.activate_key(control, "delete")
        self.assertEqual((control.text, control.key_page), ("emai", "main"))
        control.text = "email Priya that "
        ui.IrisControl.activate_key(control, "delete_word")
        self.assertEqual((control.text, control.key_page), ("email Priya ", "main"))


if __name__ == "__main__":
    unittest.main()