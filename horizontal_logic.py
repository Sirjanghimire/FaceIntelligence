"""Horizontal iris calibration, one-axis movement, selection and keyboard layout."""
from collections import deque
import json
import math
from pathlib import Path


def calibrate_horizontal(samples):
    """Map looking left/right inside the eyes to signed movement."""
    center, left, right = (samples[key] for key in ("center", "left", "right"))
    sign = 1 if right > left else -1
    spans = {"left": (center - left) * sign,
             "right": (right - center) * sign}
    if min(spans.values()) < .018:
        raise ValueError("Horizontal iris signal is too weak. Move closer to the camera, light both eyes, and retry.")
    return {"model": "horizontal-iris-v1", "center": center, "sign": sign, "span": spans}


def blink_thresholds(open_ears, closed_ears, fallback):
    """Conservative thresholds avoid interpreting a sideways squint as a blink."""
    if closed_ears is not None:
        gaps = [opened - closed for opened, closed in zip(open_ears, closed_ears)]
        if all(gap >= .035 for gap in gaps):
            return [closed + .35 * gap for closed, gap in zip(closed_ears, gaps)], True
    return [max(.04, min(fallback, opened * .68)) for opened in open_ears], False


def load_calibration(path):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if data.get("model") != "horizontal-iris-v1":
        raise ValueError("Run python calibrate.py for horizontal-only iris control.")
    if data.get("sign") not in (-1, 1) or set(data.get("span", {})) != {"left", "right"}:
        raise ValueError("Invalid iris calibration. Run python calibrate.py again.")
    if min(data["span"].values()) <= 0:
        raise ValueError("Invalid iris calibration. Run python calibrate.py again.")
    return data


class HorizontalDriver:
    """One iris direction controls either horizontal OR vertical screen motion."""
    def __init__(self, calibration, length, speed, config):
        self.cal = calibration
        self.length = length
        self.speed = speed
        self.cfg = config
        self.position = length / 2
        self.velocity = 0.
        self.history = deque(maxlen=3)
        self.last_time = None
        self.direction = 0.

    def sync(self, position):
        self.position = max(8., min(float(self.length - 9), float(position)))
        self.pause()

    def pause(self):
        self.velocity = 0.
        self.history.clear()
        self.last_time = None
        self.direction = 0.

    def move(self, eye_x, now):
        if eye_x is None:
            self.pause()
            return round(self.position)
        signed = (eye_x - self.cal["center"]) * self.cal["sign"]
        self.history.append(signed)
        filtered = sorted(self.history)[len(self.history)//2]
        side = "right" if filtered >= 0 else "left"
        raw_side = "right" if signed >= 0 else "left"
        magnitude = min(1.5, abs(filtered) / self.cal["span"][side])
        self.direction = signed / self.cal["span"][raw_side]
        dt = 0. if self.last_time is None else min(max(now - self.last_time, 0.), .07)
        self.last_time = now
        deadzone = self.cfg["deadzone"]
        if abs(self.direction) <= deadzone or magnitude <= deadzone:
            self.velocity = 0.
        else:
            target = math.copysign(min(1., ((magnitude - deadzone) / (1 - deadzone)) ** self.cfg["curve"]), filtered)
            self.velocity += (1 - math.exp(-dt / self.cfg["acceleration_s"])) * (target - self.velocity)
        self.position = max(8., min(self.length - 9., self.position + self.velocity * self.speed * self.length * dt))
        return round(self.position)


class FocusStepper:
    """Tap one choice with a glance; holding the glance repeats at a fixed pace."""
    def __init__(self, calibration, width, config, count):
        self.cal = calibration
        self.width = width
        self.cfg = config
        self.reset(count)

    def focus_x(self):
        gap, margin = 7, 8
        tile_width = (self.width - 2 * margin - gap * (self.count - 1)) / self.count
        return margin + self.index * (tile_width + gap) + tile_width / 2

    def reset(self, count, index=None):
        self.count = count
        self.index = count // 2 if index is None else max(0, min(count - 1, index))
        self.marker_x = self.focus_x()
        self.armed = False
        self.hold_direction = 0
        self.hold_since = None
        self.next_repeat = None
        self.center_since = None
        self.last_time = None
        self.is_neutral = False
        self.settle_until = None

    def clear_hold(self):
        self.hold_direction = 0
        self.hold_since = None
        self.next_repeat = None

    def step(self, direction):
        self.index = max(0, min(self.count - 1, self.index + direction))

    def pause(self):
        self.armed = False
        self.freeze()

    def freeze(self):
        self.clear_hold()
        self.center_since = None
        self.last_time = None
        self.is_neutral = False
        self.marker_x = self.focus_x()

    def update(self, eye_x, now, count):
        if count != self.count:
            self.reset(count)
        if eye_x is None:
            self.pause()
            return self.index
        if self.settle_until is not None:
            if now < self.settle_until:
                return self.index
            self.settle_until = None
        signed = (eye_x - self.cal["center"]) * self.cal["sign"]
        side = "right" if signed >= 0 else "left"
        gaze = signed / self.cal["span"][side]
        release = self.cfg["nav_release"]
        trigger = self.cfg["nav_trigger"]
        self.is_neutral = abs(gaze) <= release
        if self.is_neutral:
            if self.center_since is None:
                self.center_since = now
            if now - self.center_since >= self.cfg["nav_release_s"]:
                self.armed = True
            self.clear_hold()
        else:
            self.center_since = None
            direction = (1 if gaze >= trigger else -1 if gaze <= -trigger else 0)
            if direction:
                if self.hold_direction != direction:
                    self.hold_direction = direction
                    self.hold_since = now
                    self.next_repeat = None
                if self.armed:
                    if self.next_repeat is None and now - self.hold_since >= self.cfg["nav_hold_s"]:
                        self.step(direction)
                        self.settle_until = now + self.cfg.get("nav_settle_s", 0.12)
                        self.next_repeat = now + self.cfg["nav_repeat_delay_s"]
                    elif self.next_repeat is not None and now >= self.next_repeat:
                        self.step(direction)
                        self.settle_until = now + self.cfg.get("nav_settle_s", 0.12)
                        self.next_repeat = now + self.cfg["nav_repeat_s"]
            else:
                self.clear_hold()
        if self.last_time is not None:
            dt = min(max(now - self.last_time, 0.), .1)
            alpha = 1 - math.exp(-dt / .05)
            self.marker_x += (self.focus_x() - self.marker_x) * alpha
        self.last_time = now
        return self.index


class LongBlink:
    """A short hold selects and a much longer one toggles global pause."""
    def __init__(self, calibration, cfg):
        self.thresholds = calibration["closed_thresholds"]
        self.cfg = cfg
        self.reset()
        self.last_select = -1e9

    def reset(self):
        self.closed_at = None
        self.open_at = None
        self.armed = False

    def update(self, signal, now):
        if signal is None:
            self.reset()
            return True, False, False
        closed = (signal["left_ear"] < self.thresholds[0] and
                  signal["right_ear"] < self.thresholds[1])
        if closed:
            self.open_at = None
            if self.armed and self.closed_at is None:
                self.closed_at = now
            return True, False, False
        if self.closed_at is not None:
            duration = now - self.closed_at
            self.closed_at = None
            self.open_at = now
            self.armed = False
            if (self.cfg["pause_blink_min_s"] <= duration <= self.cfg["pause_blink_max_s"]
                    and now - self.last_select >= self.cfg["cooldown_s"]):
                self.last_select = now
                return False, False, True
            if (self.cfg["long_blink_min_s"] <= duration <= self.cfg["long_blink_max_s"]
                    and now - self.last_select >= self.cfg["cooldown_s"]):
                self.last_select = now
                return False, True, False
        if not self.armed:
            if self.open_at is None:
                self.open_at = now
            if now - self.open_at >= .18:
                self.armed = True
        return False, False, False


class DoubleBlink:
    """Two short both-eye closures delete a word; a held blink never counts."""
    def __init__(self, calibration, cfg):
        self.thresholds = calibration["closed_thresholds"]
        self.minimum = cfg.get("double_blink_min_s", .06)
        self.maximum = min(cfg.get("double_blink_max_s", .28),
                           cfg["long_blink_min_s"] - .03)
        self.gap_max = cfg.get("double_blink_gap_s", .45)
        self.reset()

    def reset(self):
        self.closed_at = None
        self.open_at = None
        self.first_opened = None
        self.armed = False

    def update(self, signal, now):
        if signal is None:
            self.reset()
            return False
        closed = (signal["left_ear"] < self.thresholds[0] and
                  signal["right_ear"] < self.thresholds[1])
        if closed:
            self.open_at = None
            if self.armed and self.closed_at is None:
                self.closed_at = now
            return False
        if self.closed_at is not None:
            started, self.closed_at = self.closed_at, None
            duration = now - started
            self.open_at, self.armed = now, False
            if self.minimum <= duration <= self.maximum:
                if self.first_opened is not None and .08 <= started - self.first_opened <= self.gap_max:
                    self.reset()
                    self.open_at = now
                    return True
                self.first_opened = now
            else:
                self.first_opened = None
        if self.first_opened is not None and now - self.first_opened > self.gap_max:
            self.first_opened = None
        if self.open_at is None:
            self.open_at = now
        if now - self.open_at >= .06:
            self.armed = True
        return False


class TripleBlink:
    """Three short both-eye closures in quick succession trigger RUN."""
    def __init__(self, calibration, cfg):
        self.thresholds = calibration["closed_thresholds"]
        self.minimum = cfg.get("double_blink_min_s", .06)
        self.maximum = min(cfg.get("double_blink_max_s", .28),
                           cfg["long_blink_min_s"] - .03)
        self.window_s = cfg.get("triple_blink_window_s", 1.1)
        self.reset()

    def reset(self):
        self.closed_at = None
        self.open_at = None
        self.opens = []
        self.armed = False

    def update(self, signal, now):
        if signal is None:
            self.reset()
            return False
        closed = (signal["left_ear"] < self.thresholds[0] and
                  signal["right_ear"] < self.thresholds[1])
        if closed:
            self.open_at = None
            if self.armed and self.closed_at is None:
                self.closed_at = now
            return False
        if self.closed_at is not None:
            started, self.closed_at = self.closed_at, None
            duration = now - started
            self.open_at, self.armed = now, False
            if self.minimum <= duration <= self.maximum:
                self.opens = [t for t in self.opens if now - t <= self.window_s]
                self.opens.append(now)
                if len(self.opens) >= 3:
                    self.reset()
                    self.open_at = now
                    return True
            else:
                self.opens = []
        self.opens = [t for t in self.opens if now - t <= self.window_s]
        if self.open_at is None:
            self.open_at = now
        if now - self.open_at >= .06:
            self.armed = True
        return False


class Dwell:
    def __init__(self, cfg):
        self.cfg = cfg
        self.anchor = None
        self.since = None
        self.fired = None

    def reset(self):
        self.anchor = self.since = self.fired = None

    def update(self, position, now):
        radius = self.cfg["dwell_radius_px"]
        if self.fired is not None:
            if abs(position - self.fired) < radius * 1.8:
                return False, 0.
            self.fired = None
        if self.anchor is None or abs(position - self.anchor) > radius:
            self.anchor, self.since = position, now
            return False, 0.
        progress = min(1., (now - self.since) / self.cfg["dwell_time_s"])
        if progress == 1.:
            self.fired = self.anchor
            return True, progress
        return False, progress


WORDS = ("i you we hello yes no please help water need want can will the to my your an email "
         "message send call today tomorrow now later thank thanks sorry good morning meeting "
         "appointment reschedule available am are is okay fine open watch schedule video for").split()
DEFAULT_QUICK_WORDS = ("email", "YouTube", "calendar", "Google", "search", "message")
NEXT = {"i": ("need", "want", "am"), "i need": ("help", "water", "to"),
        "please": ("help", "send", "call"), "thank": ("you", "the"),
        "send": ("an", "email", "message"), "send an": ("email", "message"),
        "open": ("email", "YouTube", "calendar"),
        "search": ("Google", "YouTube", "for"),
        "watch": ("YouTube", "video", "now"),
        "schedule": ("calendar", "meeting", "appointment")}


def predict_words(text, learned=(), quick_words=DEFAULT_QUICK_WORDS, external=None):
    """Return up to 3 next-word tiles. `external` (e.g. from Gemini) is merged
    ahead of the local vocabulary; a bad external value is ignored."""
    prefix = text.lower().split()[-1] if text and not text.endswith(" ") else ""
    vocabulary = list(dict.fromkeys([*learned, *WORDS, *quick_words]))
    if isinstance(external, (list, tuple)):
        clean = [str(w).strip() for w in external if isinstance(w, str) and str(w).strip()]
        if prefix:
            clean = [w for w in clean if w.lower().startswith(prefix)]
        vocabulary = list(dict.fromkeys([*clean, *vocabulary]))
    if prefix:
        return [word for word in vocabulary if word.lower().startswith(prefix)][:3]
    terms = text.lower().split()
    key = " ".join(terms[-2:])
    context = NEXT.get(key, NEXT.get(terms[-1], ()) if terms else ())
    return list(dict.fromkeys([*context, *vocabulary]))[:3]


def delete_visible_character(text):
    return text.rstrip()[:-1]


def delete_last_word(text):
    text = text.rstrip()
    parts = text.rsplit(None, 1)
    return parts[0].rstrip() + " " if len(parts) == 2 else ""


def keyboard_tiles(page, group, text, learned=(), quick_words=DEFAULT_QUICK_WORDS, external=None):
    shortcuts = list(dict.fromkeys(word.strip() for word in quick_words
                                   if isinstance(word, str) and word.strip()))[:6]
    words = predict_words(text, learned, shortcuts, external=external) + ["", "", ""]
    if page == "main":
        return [(w.upper() or "·", "word:" + w) for w in words[:2]] + [
            ("A–F", "group:ABCDEF"), ("G–L", "group:GHIJKL"),
            ("M–R", "group:MNOPQR"), ("S–X", "group:STUVWX"),
            ("Y/Z", "group:YZ"), ("0–9", "page:digits1"),
            ("SYM", "page:symbols"), ("SPACE", "space"),
            ("DEL", "delete"), ("RUN", "run"), ("QUICK", "page:quick"),
            ("BACK", "page:main")]
    if page == "quick":
        return [(word.upper(), "word:" + word) for word in shortcuts] + [
            ("DEL", "delete"), ("RUN", "run"), ("BACK", "page:main")]
    if page == "letters":
        keys = [(char, "letter:" + char.lower()) for char in group]
        if len(group) < 6:
            keys += [("SPACE", "space"), ("DEL", "delete")]
        return (keys + [("BACK", "page:main")])[:7]
    if page == "symbols":
        return [("123", "page:digits1"), ("?", "letter:?"), (",", "letter:,"),
                ("-", "letter:-"), ("!", "letter:!"), (".", "letter:."),
                ("@", "letter:@"), ("CAP", "caps"), ("BACK", "page:main")][:9]
    if page == "digits1":
        return [(number, "letter:" + number) for number in "123456"] + \
               [("NEXT", "page:digits2"), ("BACK", "page:main")]
    if page == "digits2":
        return [(number, "letter:" + number) for number in "7890"] + [
            ("SPACE", "space"), ("BACK", "page:digits1"), ("SYM", "page:symbols")]
    raise ValueError("Unknown keyboard page")