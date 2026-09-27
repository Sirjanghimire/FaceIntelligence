"""Horizontal iris input, app-centric home screen, review-first assistant."""
from concurrent.futures import ThreadPoolExecutor
import json
import os
import statistics
import textwrap
import threading
import time
import tkinter as tk
from pathlib import Path

import pyautogui

from assistant_core import Assistant
from horizontal_logic import (DEFAULT_QUICK_WORDS, DoubleBlink, Dwell,
                              FocusStepper, HorizontalDriver, LongBlink,
                              TripleBlink, delete_last_word,
                              delete_visible_character, keyboard_tiles,
                              load_calibration)
from iris_tracking import LatestIrisTracker
from jeff_agent import predict_words_remote

HERE = Path(__file__).resolve().parent


class IrisControl:
    def __init__(self):
        self.cfg = json.loads((HERE / "config.json").read_text(encoding="utf-8"))
        self.cal = load_calibration(HERE / "calibration.json")
        self.selection = self.cfg["selection_mode"]
        if self.selection == "auto":
            self.selection = "blink" if self.cal["blink_reliable"] else "dwell"
        if self.selection not in ("blink", "dwell"):
            raise ValueError("selection_mode must be auto, blink, or dwell")
        self.screen = tuple(pyautogui.size())
        self.sw, self.sh = self.screen
        self.mouse = tuple(pyautogui.position())
        self.last_mouse_sent = self.mouse
        self.tracker = LatestIrisTracker(self.cfg["camera_index"])
        self.blink = LongBlink(self.cal, self.cfg)
        self.double_blink = DoubleBlink(self.cal, self.cfg)
        self.triple_blink = TripleBlink(self.cal, self.cfg)
        self.menu_dwell = Dwell(self.cfg)
        cursor_dwell_cfg = {**self.cfg, "dwell_time_s": 2.2}
        self.cursor_dwell = Dwell(cursor_dwell_cfg)
        self.nav = FocusStepper(self.cal, self.sw, self.cfg, 7)
        self.pointer = HorizontalDriver(self.cal, self.sw, self.cfg["speed_x"], self.cfg)
        self.mode = "menu"
        self.menu_page = "home"
        self.key_page = "main"
        self.contact_page = 0
        self.selected_contact = None
        self.selected_topic = ""
        self.group = ""
        self.text = ""
        self.deletion_undo = None
        self.learned = []
        self.capitalize_next = False
        self.precision = False
        self.paused = False
        self.pause_ready = False
        self.pause_side_since = None
        self.pause_center_since = None
        self.pause_progress = 0.
        self.safe = False
        self.face_visible = False
        self.dwell_progress = 0.
        self.recenter_started = None
        self.recenter_readings = []
        self.flash = ""
        self.flash_until = 0.
        self.running = True
        self.assistant = Assistant(self.cfg, HERE)
        self.favorites = self._load_favorites()
        self.executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="iris-assistant")
        self.pending_job = None
        self.stage = "idle"
        self.plan = None
        self.suggestions = []
        self.result = ""
        self.review_page = 0
        self._gemini_lock = threading.Lock()
        self._gemini_pending = None
        self._gemini_external = None
        self._gemini_last_fragment = None
        self._gemini_last_started = 0.
        self.nav.reset(len(self.tiles()), index=self._default_index())
        self.menu_dwell.fired = self.nav.index * 100
        pyautogui.FAILSAFE = True
        pyautogui.PAUSE = 0
        self.root = tk.Tk()
        self.root.title("Horizontal iris controls")
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.geometry(f"{self.sw}x170+0+0")
        self.root.bind("<Escape>", lambda _: self.quit())
        self.root.protocol("WM_DELETE_WINDOW", self.quit)
        self.bar = tk.Canvas(self.root, bg="#12233b", height=170,
                             highlightthickness=0, cursor="none")
        self.bar.pack(fill="both", expand=True)
        self.root.after(16, self.tick)

    def _load_favorites(self):
        path = HERE / "favorites.json"
        if not path.exists():
            return {"songs": [], "movies": []}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return {"songs": list(data.get("songs", []))[:6],
                    "movies": list(data.get("movies", []))[:6]}
        except Exception:
            return {"songs": [], "movies": []}

    def _default_index(self):
        if self.mode == "assistant" and self.stage in ("review", "send_confirmation"):
            return 0
        if self.mode == "keyboard" and self.key_page == "contacts":
            return 0
        count = len(self.tiles())
        return count // 2

    def quit(self):
        if self.running:
            self.running = False
            self.executor.shutdown(wait=False, cancel_futures=True)
            self.tracker.close()
            self.root.destroy()

    def message(self, text):
        self.flash, self.flash_until = text, time.monotonic() + 2.6

    def reset_navigation(self):
        self.double_blink.reset()
        self.triple_blink.reset()
        self.nav.reset(len(self.tiles()), index=self._default_index())
        self.menu_dwell.reset()
        self.menu_dwell.fired = self.nav.index * 100
        self.dwell_progress = 0.

    def set_paused(self, paused):
        self.paused = paused
        self.nav.pause()
        self.pointer.pause()
        self.menu_dwell.reset()
        self.menu_dwell.fired = self.nav.index * 100
        self.cursor_dwell.reset()
        self.blink.reset()
        self.double_blink.reset()
        self.triple_blink.reset()
        self.pause_ready = False
        self.pause_side_since = None
        self.pause_center_since = None
        self.pause_progress = 0.
        height = (170 if paused else 42 if self.mode.startswith("cursor_")
                  else 330 if self.mode == "assistant" else 170)
        self.root.geometry(f"{self.sw}x{height}+0+0")
        self.bar.config(height=height)

    def update_pause_dwell(self, eye_x, now):
        signed = (eye_x - self.cal["center"]) * self.cal["sign"]
        side = "right" if signed >= 0 else "left"
        magnitude = abs(signed) / self.cal["span"][side]
        if magnitude >= .48:
            if self.pause_side_since is None:
                self.pause_side_since = now
            if now - self.pause_side_since >= .12:
                self.pause_ready = True
            self.pause_center_since = None
            self.pause_progress = 0.
        elif magnitude <= self.cfg["nav_release"] and self.pause_ready:
            if self.pause_center_since is None:
                self.pause_center_since = now
            self.pause_progress = min(1., (now - self.pause_center_since) / .85)
            if self.pause_progress >= 1.:
                self.set_paused(False)
        else:
            self.pause_side_since = None
            self.pause_center_since = None
            self.pause_progress = 0.

    def set_mode(self, mode):
        self.mode = mode
        height = 42 if mode.startswith("cursor_") else 330 if mode == "assistant" else 170
        self.root.geometry(f"{self.sw}x{height}+0+0")
        self.bar.config(height=height)
        self.blink.reset()
        self.double_blink.reset()
        self.triple_blink.reset()
        if mode.startswith("cursor_"):
            self.mouse = tuple(pyautogui.position())
            self.pointer = HorizontalDriver(
                self.cal, self.sw if mode == "cursor_x" else self.sh,
                self.cfg["speed_x" if mode == "cursor_x" else "speed_y"] *
                (self.cfg["fine_speed_factor"] if self.precision else 1.),
                self.cfg)
            self.pointer.sync(self.mouse[0 if mode == "cursor_x" else 1])
            self.cursor_dwell.reset()
            self.menu_dwell.reset()
        elif mode in ("menu", "keyboard", "assistant"):
            self.reset_navigation()
        else:
            self.nav.pause()

    def menu_tiles(self):
        if self.menu_page == "home":
            return [("EMAIL", "menu:email"), ("YOUTUBE", "menu:youtube"),
                    ("GOOGLE", "menu:google"), ("ALPHABETS", "menu:alphabets"),
                    ("UNDO", "menu:undo"), ("RUN", "menu:run"),
                    ("CURSOR", "menu:cursor")]
        if self.menu_page == "cursor":
            return [("MOVE X", "cursor_x"), ("MOVE Y", "cursor_y"),
                    ("CLICK", "click"), ("R-CLICK", "right_click"),
                    ("SCROLL ↑", "scroll_up"), ("SCROLL ↓", "scroll_down"),
                    ("PASTE", "paste"), ("FINE" if not self.precision else "FAST", "precision"),
                    ("RE-CENTER", "recenter"), ("SAFE" if not self.safe else "UNSAFE", "safe"),
                    ("BACK", "menu:back")]
        if self.menu_page == "email_recipients":
            contacts = self.assistant.contacts[:5]
            return ([("BACK", "menu:back")]
                    + [(c["name"][:14].upper(), "recipient:" + str(i))
                       for i, c in enumerate(contacts)]
                    + [("TYPE", "recipient_type"), ("OPEN GMAIL", "menu:open_gmail")])
        if self.menu_page == "email_topics":
            topics = [t for t in self.cfg.get(
                "email_topics",
                ["emergency", "food", "wellbeing", "check in", "contact me"])
                if isinstance(t, str) and t.strip()]
            tiles = [("BACK", "menu:back")]
            for t in topics[:6]:
                tiles.append((t.upper(), "topic:" + t))
            tiles.append(("TYPE", "topic_type"))
            return tiles
        if self.menu_page == "youtube":
            return [("BACK", "menu:back"), ("FAV SONGS", "yt:songs"),
                    ("MOVIES", "yt:movies"), ("TYPE", "yt:type")]
        if self.menu_page == "youtube_songs":
            songs = self.favorites.get("songs", [])[:6]
            return ([("BACK", "menu:back")]
                    + [(s[:18].upper(), "play:" + s) for s in songs]
                    + [("TYPE", "yt:type")])
        if self.menu_page == "youtube_movies":
            movies = self.favorites.get("movies", [])[:6]
            return ([("BACK", "menu:back")]
                    + [(m[:18].upper(), "play:" + m) for m in movies]
                    + [("TYPE", "yt:type")])
        return [("BACK", "menu:back")]
# --- END CHUNK A ---

    def assistant_tiles(self):
        if self.stage == "working":
            return [("CANCEL", "cancel"), ("THINKING", "noop")]
        if self.stage == "running":
            return [("WORKING", "noop")]
        if self.stage == "review":
            pages = self.review_pages()
            if self.review_page < len(pages) - 1:
                return [("CANCEL", "cancel"), ("EDIT", "edit"),
                        ("IDEAS", "ideas"), ("NEXT", "next_page")]
            first = ("PREV", "prev_page") if self.review_page else ("CANCEL", "cancel")
            if self.plan and self.plan.action == "draft_email":
                if self.assistant.can_send(self.plan):
                    return [first, ("EDIT", "edit"), ("IDEAS", "ideas"),
                            ("SEND", "request_send")]
                return [first, ("EDIT", "edit"), ("IDEAS", "ideas"), ("GMAIL", "go")]
            return [first, ("EDIT", "edit"), ("IDEAS", "ideas"), ("GO", "go")]
        if self.stage == "send_confirmation":
            if self.review_page < len(self.review_pages()) - 1:
                return [("NO, BACK", "cancel_send"), ("NEXT", "next_page")]
            return [("NO, BACK", "cancel_send"), ("YES, SEND", "send")]
        if self.stage == "ideas":
            return [("EDIT", "edit")] + [
                (idea[:22].upper(), "idea:" + str(i))
                for i, idea in enumerate(self.suggestions[:3])
            ] + [("BACK", "back_review")]
        if self.stage == "done":
            return [("MENU", "menu"), ("EDIT", "edit"), ("NEW TASK", "new")]
        return [("CANCEL", "cancel"), ("EDIT", "edit"), ("IDEAS", "ideas")]

    def review_pages(self):
        if not self.plan:
            return [""]
        detail = self.plan.details or self.plan.missing or self.plan.summary
        lines = []
        for paragraph in detail.splitlines():
            lines.extend(textwrap.wrap(paragraph,
                                       width=max(34, min(72, self.sw // 13)),
                                       break_long_words=True) or [""])
        return ["\n".join(lines[i:i+5]) for i in range(0, len(lines), 5)] or [""]

    def contact_tiles(self):
        contacts = self.assistant.contacts
        if not contacts:
            return [("BACK", "contact_back"), ("TYPE NAME", "contact_manual"),
                    ("OPEN GMAIL", "contact_open_gmail")]
        page = self.contact_page
        start = page * 5
        result = [("BACK", "contact_back")]
        result += [(c["name"][:20].upper(), "contact:" + str(i))
                   for i, c in enumerate(contacts[start:start+5], start)]
        if page:
            result.append(("PREV", "contact_prev"))
        if start + 5 < len(contacts):
            result.append(("NEXT", "contact_next"))
        return result + [("TYPE NAME", "contact_manual")]

    def displayed_text(self):
        contact = getattr(self, "selected_contact", None)
        if contact:
            prefix = "email " + contact["email"]
            if self.text[:len(prefix)].casefold() == prefix.casefold():
                return "email " + contact["name"] + self.text[len(prefix):]
        return self.text

    def _current_external_words(self):
        with self._gemini_lock:
            if (self._gemini_last_fragment == self.text
                    and self._gemini_external):
                return list(self._gemini_external)
        return None

    def _kick_gemini_words(self, text):
        text = (text or "").strip()
        if not text:
            return
        if not (os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
                or os.environ.get("OPENAI_API_KEY")):
            return
        now = time.monotonic()
        with self._gemini_lock:
            if self._gemini_pending is not None and not self._gemini_pending.done():
                return
            if text == self._gemini_last_fragment and self._gemini_external:
                return
            if now - self._gemini_last_started < 0.7:
                return
            self._gemini_last_started = now
            self._gemini_pending = self.executor.submit(predict_words_remote, text, 3)

    def _poll_gemini_words(self):
        with self._gemini_lock:
            pending = self._gemini_pending
            if pending is None or not pending.done():
                return
            self._gemini_pending = None
        try:
            words = pending.result()
        except Exception:
            words = []
        if words:
            with self._gemini_lock:
                self._gemini_external = list(words)[:3]
                self._gemini_last_fragment = self.text

    def tiles(self):
        if self.mode == "menu":
            return self.menu_tiles()
        if self.mode == "assistant":
            return self.assistant_tiles()
        if self.key_page == "contacts":
            return self.contact_tiles()
        external = self._current_external_words()
        return keyboard_tiles(self.key_page, self.group, self.text, self.learned,
                              self.cfg.get("quick_words", DEFAULT_QUICK_WORDS),
                              external=external)

    def focused_action(self):
        tiles = self.tiles()
        index = min(len(tiles) - 1, self.nav.index)
        return index, tiles[index][1]

    def desktop_click(self, button):
        if self.safe:
            self.message("SAFE ON · DESKTOP ACTION BLOCKED")
            return
        self.root.withdraw()
        self.root.update_idletasks()
        try:
            pyautogui.click(*self.mouse, button=button)
        except pyautogui.FailSafeException:
            self.safe = True
            self.message("MOUSE FAILSAFE · MOVE PHYSICAL MOUSE AWAY FROM CORNER")
            return
        finally:
            self.root.deiconify()
            self.root.lift()
        self.last_mouse_sent = self.mouse
        self.message("CLICKED")

    def _undo_last_delete(self):
        if self.deletion_undo is not None:
            self.text, self.deletion_undo = self.deletion_undo, None
            self.message("RESTORED")
        else:
            self.message("NOTHING TO UNDO")

    def _run_text(self, raw):
        text = " ".join((raw or "").strip().split())[:500]
        if not text:
            self.message("NOTHING TO RUN")
            return
        self.start_job("prepare", self.assistant.prepare, text)

    def _email_topic_send(self, topic):
        contact = self.selected_contact
        if contact is None:
            self.message("CHOOSE A RECIPIENT FIRST")
            return
        intent = f"{topic} update"
        message = f"email {contact['email'] or contact['name']} about {topic}"
        self.start_job("prepare", self.assistant.prepare, message)
# --- END CHUNK B ---

    def activate_menu(self, action):
        if action in ("cursor_x", "cursor_y"):
            self.set_mode(action)
            return
        if action == "menu:home":
            self.menu_page = "home"
            self.reset_navigation()
        elif action == "menu:cursor":
            self.menu_page = "cursor"
            self.reset_navigation()
        elif action == "menu:back":
            self.menu_page = "home"
            self.selected_contact = None
            self.selected_topic = ""
            self.reset_navigation()
        elif action == "menu:email":
            self.menu_page = "email_recipients"
            self.selected_contact = None
            self.reset_navigation()
        elif action == "menu:youtube":
            self.menu_page = "youtube"
            self.reset_navigation()
        elif action == "menu:google":
            self._run_text("open Google")
        elif action == "menu:alphabets":
            self.text = ""
            self.deletion_undo = None
            self.selected_contact = None
            self.key_page = "main"
            self.set_mode("keyboard")
        elif action == "menu:undo":
            self._undo_last_delete()
        elif action == "menu:run":
            self._run_text(self.text)
        elif action == "menu:open_gmail":
            self._run_text("open Gmail")
        elif action.startswith("recipient:"):
            self.selected_contact = self.assistant.contacts[int(action.split(":", 1)[1])]
            self.text = "email " + self.selected_contact["email"] + " about "
            self.menu_page = "email_topics"
            self.reset_navigation()
        elif action == "recipient_type":
            if self.selected_contact:
                self.text = "email " + self.selected_contact["email"] + " that "
            else:
                self.text = "email "
            self.selected_contact = None
            self.key_page = "main"
            self.set_mode("keyboard")
        elif action.startswith("topic:"):
            topic = action.split(":", 1)[1]
            self.selected_topic = topic
            self._email_topic_send(topic)
        elif action == "topic_type":
            self.key_page = "main"
            self.set_mode("keyboard")
        elif action == "yt:songs":
            self.menu_page = "youtube_songs"
            self.reset_navigation()
        elif action == "yt:movies":
            self.menu_page = "youtube_movies"
            self.reset_navigation()
        elif action == "yt:type":
            self.text = "play YouTube "
            self.key_page = "main"
            self.set_mode("keyboard")
        elif action.startswith("play:"):
            query = action.split(":", 1)[1]
            self._run_text("play YouTube " + query)
        elif action == "click":
            self.desktop_click("left")
        elif action == "right_click":
            self.desktop_click("right")
        elif action == "keyboard":
            self.key_page = "main"
            self.set_mode("keyboard")
        elif action == "paste":
            if not self.safe:
                pyautogui.hotkey("ctrl", "v")
                self.message("PASTED INTO FOCUSED APP")
        elif action in ("scroll_up", "scroll_down"):
            if not self.safe:
                pyautogui.scroll(4 if action == "scroll_up" else -4)
        elif action == "precision":
            self.precision = not self.precision
            self.message("FINE CURSOR ON" if self.precision else "FAST CURSOR ON")
        elif action == "safe":
            self.safe = not self.safe
            self.message("SAFE ON" if self.safe else "DESKTOP ACTIONS ENABLED")
        elif action == "recenter":
            self.recenter_started = time.monotonic()
            self.recenter_readings = []
            self.set_mode("recenter")
        elif action == "pause":
            self.set_paused(True)
        elif action == "quit":
            self.quit()

    def delete_text(self, whole_word=False):
        prefix = ""
        contact = getattr(self, "selected_contact", None)
        if contact:
            expected = "email " + contact["email"] + " that "
            if self.text[:len(expected)].casefold() == expected.casefold():
                prefix = self.text[:len(expected)]
        remove = delete_last_word if whole_word else delete_visible_character
        updated = prefix + remove(self.text[len(prefix):])
        if updated != self.text:
            self.deletion_undo = self.text
            self.text = updated
            return True
        return False

    def activate_key(self, action):
        previous_page = self.key_page
        if action in ("clear", "space", "contact_manual", "contact_open_gmail") or \
                action.startswith(("word:", "letter:", "contact:")):
            self.deletion_undo = None
        if action == "run":
            self._run_text(self.text)
        elif action == "contact_back":
            self.key_page = "quick"
        elif action == "contact_manual":
            self.selected_contact = None
            self.text, self.key_page = "email ", "main"
        elif action == "contact_open_gmail":
            self.selected_contact = None
            self._run_text("open Gmail")
        elif action == "contact_next":
            self.contact_page += 1
            self.reset_navigation()
        elif action == "contact_prev":
            self.contact_page -= 1
            self.reset_navigation()
        elif action.startswith("contact:"):
            chosen = self.assistant.contacts[int(action.split(":", 1)[1])]
            self.selected_contact = chosen
            self.text = "email " + chosen["email"] + " that "
            self.key_page = "main"
        elif action.startswith("word:"):
            word = action[5:]
            if word.lower() == "email" and not self.text.strip():
                self.selected_contact = None
                self.contact_page = 0
                self.key_page = "contacts"
            elif word:
                prefix = self.text.rsplit(" ", 1)[-1] if not self.text.endswith(" ") else ""
                if prefix:
                    self.text = self.text[:-len(prefix)]
                self.text += (word[0].upper() + word[1:] if self.capitalize_next else word) + " "
                self.capitalize_next = False
                if word not in self.learned:
                    self.learned.insert(0, word)
                self._kick_gemini_words(self.text)
        elif action.startswith("group:"):
            self.group, self.key_page = action[6:], "letters"
        elif action.startswith("page:"):
            self.key_page = action[5:]
        elif action.startswith("letter:"):
            letter = action[7:]
            self.text += letter.upper() if self.capitalize_next else letter
            self.capitalize_next = False
            self.key_page = "main"
            self._kick_gemini_words(self.text)
        elif action == "caps":
            self.capitalize_next = True
            self.key_page = "main"
        elif action == "space":
            self.text += " "
            self.key_page = "main"
            self._kick_gemini_words(self.text)
        elif action == "delete":
            self.delete_text()
            self.key_page = "main"
        elif action == "delete_word":
            self.delete_text(whole_word=True)
            self.key_page = "main"
        elif action == "undo_delete":
            self._undo_last_delete()
            self.key_page = "main"
        elif action == "clear":
            self.selected_contact = None
            self.text, self.key_page = "", "main"
        elif action == "copy":
            self.root.clipboard_clear()
            self.root.clipboard_append(self.text)
            self.root.update()
            self.message("COPIED · HIDE, CLICK TARGET, THEN PASTE")
        elif action == "hide":
            self.menu_page = "home"
            self.set_mode("menu")
        if self.mode == "keyboard" and self.key_page != previous_page:
            self.reset_navigation()

    def start_job(self, kind, function, *args):
        if self.pending_job is not None and not self.pending_job[0].done():
            return
        self.stage = "running" if kind == "execute" else "working"
        self.pending_job = (self.executor.submit(function, *args), kind)
        self.set_mode("assistant")

    def poll_job(self):
        if self.pending_job is None or not self.pending_job[0].done():
            return
        future, kind = self.pending_job
        self.pending_job = None
        try:
            result = future.result()
        except Exception as exc:
            self.result = "Task stopped: " + str(exc)[:220]
            self.stage = "done"
        else:
            if kind == "prepare":
                self.plan = result
                self.review_page = 0
                if (result.ready and result.action == "draft_email"
                        and self.assistant.wants_auto_send(result)):
                    self.result = self.assistant.execute(result, send=True)
                    self.stage = "done"
                else:
                    self.stage = "review" if result.ready else "need"
            elif kind == "ideas":
                self.suggestions = [s for s in dict.fromkeys(result) if s.strip()][:3]
                self.stage = "ideas" if self.suggestions else "need"
            elif kind == "execute":
                self.result = result
                self.stage = "done"
        if self.mode == "assistant" and not self.paused:
            self.set_mode("assistant")
        elif self.mode == "assistant":
            self.nav.reset(len(self.tiles()), index=0)
            self.menu_dwell.fired = 0

    def activate_assistant(self, action):
        if action == "noop":
            return
        if action in ("cancel", "menu"):
            self.menu_page = "home"
            self.set_mode("menu")
        elif action == "edit":
            self.key_page = "main"
            self.set_mode("keyboard")
        elif action == "new":
            self.text = ""
            self.deletion_undo = None
            self.selected_contact = None
            self.key_page = "quick"
            self.set_mode("keyboard")
        elif action == "ideas":
            self.start_job("ideas", self.assistant.suggestions, self.text)
        elif action.startswith("idea:"):
            self.text = self.suggestions[int(action[5:])]
            self.deletion_undo = None
            self.selected_contact = None
            self.start_job("prepare", self.assistant.prepare, self.text)
        elif action == "back_review":
            self.stage = "review" if self.plan and self.plan.ready else "need"
            self.set_mode("assistant")
        elif action == "next_page" and self.review_page < len(self.review_pages()) - 1:
            self.review_page += 1
            self.set_mode("assistant")
        elif action == "prev_page" and self.review_page:
            self.review_page -= 1
            self.set_mode("assistant")
        elif action == "go" and self.stage == "review" and self.plan and self.plan.ready and \
                self.review_page == len(self.review_pages()) - 1:
            self.start_job("execute", self.assistant.execute, self.plan)
        elif action == "request_send" and self.stage == "review" and self.plan and \
                self.assistant.can_send(self.plan) and \
                self.review_page == len(self.review_pages()) - 1:
            self.stage = "send_confirmation"
            self.review_page = 0
            self.set_mode("assistant")
        elif action == "cancel_send":
            self.stage = "review"
            self.set_mode("assistant")
        elif action == "send" and self.stage == "send_confirmation" and \
                self.review_page == len(self.review_pages()) - 1:
            self.start_job("execute", lambda: self.assistant.execute(self.plan, send=True))
# --- END CHUNK C ---

    def tick(self):
        if not self.running:
            return
        self.poll_job()
        self._poll_gemini_words()
        if (self.mode == "keyboard"
                and self.key_page not in ("contacts",)
                and self.selection == "blink"
                and not self.paused
                and not self.text.endswith(" ")):
            pass  # Gemini prefetch already kicked on edit
        try:
            frame, signal = self.tracker.read()
        except RuntimeError as exc:
            print("Horizontal iris control:", exc)
            self.quit()
            return
        if frame is None:
            self.quit()
            return
        now = time.monotonic()
        self.face_visible = signal is not None
        frozen, selected, pause_toggle = self.blink.update(signal, now)
        if self.selection != "blink":
            selected = False
        thresholds = self.cal["closed_thresholds"]
        eyes_open = (signal is not None and not frozen and
                     signal["left_ear"] >= thresholds[0] and
                     signal["right_ear"] >= thresholds[1])

        delete_word = False
        if (self.mode == "keyboard" and self.key_page != "contacts"
                and self.selection == "blink" and not self.paused
                and self.cfg.get("double_blink_delete", True)):
            delete_word = self.double_blink.update(signal, now)
        else:
            self.double_blink.reset()

        run_now = False
        if (self.selection == "blink" and not self.paused
                and self.cfg.get("triple_blink_run", True)
                and self.mode in ("menu", "keyboard", "assistant")):
            run_now = self.triple_blink.update(signal, now)
        else:
            self.triple_blink.reset()

        if pause_toggle and self.selection == "blink":
            self.set_paused(not self.paused)
            self.draw(now)
            self.root.after(16, self.tick)
            return
        if self.paused:
            if selected:
                self.set_paused(False)
            elif self.selection == "dwell" and eyes_open:
                self.update_pause_dwell(signal["eye_x"], now)
            elif not eyes_open:
                self.pause_ready = False
                self.pause_side_since = None
                self.pause_center_since = None
                self.pause_progress = 0.
            self.draw(now)
            self.root.after(16, self.tick)
            return
        if run_now:
            self.blink.reset()
            self.nav.freeze()
            self.menu_dwell.reset()
            self.dwell_progress = 0.
            if self.mode == "assistant":
                if (self.stage in ("review", "send_confirmation")
                        and self.review_page == len(self.review_pages()) - 1):
                    _, action = self.focused_action()
                    if action in ("go", "request_send", "send"):
                        self.activate_assistant(action)
                    else:
                        self.message("NOTHING TO RUN")
                elif self.stage == "ideas" and self.suggestions:
                    self.activate_assistant("idea:0")
                else:
                    self.message("NOTHING TO RUN")
            elif self.mode == "keyboard":
                self._run_text(self.text)
            else:
                self._run_text(self.text)
            self.draw(now)
            self.root.after(16, self.tick)
            return
        if delete_word:
            changed = self.delete_text(whole_word=True)
            self.blink.reset()
            self.nav.freeze()
            self.menu_dwell.reset()
            self.dwell_progress = 0.
            self.message("WORD DELETED · CURSOR → UNDO TO RESTORE" if changed
                         else "NO WORD TO DELETE")
            self.draw(now)
            self.root.after(16, self.tick)
            return
        if self.mode == "recenter":
            if eyes_open and now - self.recenter_started >= .65:
                self.recenter_readings.append(signal["eye_x"])
            if now - self.recenter_started >= 2.3:
                if len(self.recenter_readings) >= 8:
                    self.cal["center"] = statistics.median(self.recenter_readings)
                    self.message("IRIS CENTER RESET")
                else:
                    self.message("RE-CENTER FAILED · EYES NOT VISIBLE")
                self.menu_page = "home"
                self.set_mode("menu")
        elif self.mode in ("menu", "keyboard", "assistant"):
            physical = tuple(pyautogui.position())
            if max(abs(a-b) for a, b in zip(physical, self.last_mouse_sent)) > 12:
                self.last_mouse_sent = self.mouse = physical
            if eyes_open and not selected:
                self.nav.update(signal["eye_x"], now, len(self.tiles()))
            elif signal is None or selected:
                self.nav.pause()
            else:
                self.nav.freeze()
            if self.selection == "dwell":
                if eyes_open and self.nav.is_neutral:
                    selected, self.dwell_progress = self.menu_dwell.update(
                        self.nav.index * 100, now)
                elif not eyes_open:
                    self.menu_dwell.reset()
                    self.menu_dwell.fired = self.nav.index * 100
                    self.dwell_progress = 0.
                else:
                    self.menu_dwell.anchor = self.menu_dwell.since = None
                    self.dwell_progress = 0.
            if selected:
                _, action = self.focused_action()
                if self.mode == "menu":
                    self.activate_menu(action)
                elif self.mode == "keyboard":
                    self.activate_key(action)
                else:
                    self.activate_assistant(action)
                if not self.running:
                    return
        else:
            physical = tuple(pyautogui.position())
            if max(abs(a-b) for a, b in zip(physical, self.last_mouse_sent)) > 12:
                self.mouse = physical
                self.pointer.sync(physical[0 if self.mode == "cursor_x" else 1])
                self.last_mouse_sent = physical
            if self.selection == "dwell" and eyes_open:
                selected, self.dwell_progress = self.cursor_dwell.update(
                    self.pointer.position, now)
            if selected:
                self.menu_page = "home"
                self.set_mode("menu")
            elif eyes_open:
                new_axis = self.pointer.move(signal["eye_x"], now)
                destination = ((new_axis, self.mouse[1]) if self.mode == "cursor_x"
                               else (self.mouse[0], new_axis))
                if destination != self.last_mouse_sent:
                    try:
                        pyautogui.moveTo(*destination)
                    except pyautogui.FailSafeException:
                        self.safe = True
                        self.set_mode("menu")
                        self.message("MOUSE FAILSAFE · MOVE PHYSICAL MOUSE AWAY FROM CORNER")
                    else:
                        self.last_mouse_sent = self.mouse = destination
            else:
                self.pointer.pause()
                self.cursor_dwell.reset()
        self.draw(now)
        self.root.after(16, self.tick)

    def draw(self, now):
        cv = self.bar
        cv.delete("all")
        if self.paused:
            cv.create_text(self.sw/2, 25, text="PAUSED · CURSOR AND KEYBOARD FROZEN",
                           fill="white", font=("Segoe UI", 17, "bold"))
            cv.create_rectangle(self.sw*.25, 48, self.sw*.75, 120,
                                fill="#3c806f", outline="#a8ffcf", width=2)
            cv.create_text(self.sw/2, 84, text="RESUME", fill="white",
                           font=("Segoe UI", 22, "bold"))
            if self.selection == "dwell":
                cv.create_rectangle(self.sw*.25, 116,
                                    self.sw*(.25 + .5*self.pause_progress), 120,
                                    fill="#b8ffbb", outline="")
            hint = ("BLINK TO RESUME · OR CLOSE BOTH EYES ~1.7s"
                    if self.selection == "blink"
                    else "LOOK TO EITHER SIDE, THEN CENTER AND HOLD TO RESUME")
            cv.create_text(self.sw/2, 147, text=hint, fill="#d4eaca",
                           font=("Segoe UI", 11, "bold"))
            return
        if self.mode.startswith("cursor_"):
            name = ("MOVE X · LEFT / RIGHT IRIS" if self.mode == "cursor_x"
                    else "MOVE Y · LEFT IRIS = UP · RIGHT IRIS = DOWN")
            cv.create_text(14, 21, text=f"{name} · CENTER=STOP · " +
                           ("BLINK=MENU · LONG BLINK=PAUSE" if self.selection == "blink"
                            else "HOLD CENTER=MENU · MENU HAS PAUSE") +
                           (" · FINE" if self.precision else " · FAST"),
                           fill="white", anchor="w", width=self.sw-28,
                           font=("Segoe UI", 11, "bold"))
            return
        if self.mode == "recenter":
            cv.create_text(self.sw / 2, 28,
                           text="LOOK AT THE CENTER DOT WITH YOUR EYES OPEN",
                           fill="white", font=("Segoe UI", 18, "bold"))
            cv.create_oval(self.sw/2-21, 64, self.sw/2+21, 106,
                           fill="#93ffd1", outline="white")
            return
        if self.mode == "assistant":
            if self.stage == "review":
                heading = "REVIEW BEFORE GO · " + self.plan.summary
            elif self.stage == "send_confirmation":
                heading = "FINAL REVIEW · SEND THIS EMAIL?"
            elif self.stage == "ideas":
                heading = "CHOOSE A SUGGESTION · YOU CAN EDIT IT BEFORE GO"
            elif self.stage in ("working", "running"):
                heading = "ASSISTANT WORKING · EYE TRACKING CONTINUES"
            elif self.stage == "done":
                heading = "TASK RESULT · TRIPLE-BLINK TO RUN AGAIN"
            else:
                heading = self.plan.summary if self.plan else "MORE DETAILS NEEDED"
        elif self.mode == "keyboard":
            if self.key_page == "contacts":
                heading = ("CHOOSE RECIPIENT · glance to a name, blink to select"
                           if self.assistant.contacts
                           else "NO SAVED CONTACTS · IMPORT A CSV, OR CHOOSE TYPE NAME")
            else:
                heading = self.displayed_text()[-145:] or \
                    "TYPE WITH LEFT / RIGHT IRIS · WORDS ON THE LEFT"
            if self.capitalize_next:
                heading = "CAP NEXT · " + heading
        else:
            if self.menu_page == "home":
                heading = "HOME · glance to step · hold to move across · triple-blink = RUN"
            elif self.menu_page == "cursor":
                heading = "CURSOR · movement, click, scroll · BACK returns home"
            elif self.menu_page == "email_recipients":
                heading = "WHO SHOULD RECEIVE THE EMAIL?"
            elif self.menu_page == "email_topics":
                contact = self.selected_contact or {}
                heading = "EMAIL " + contact.get("name", "") + " · CHOOSE A TOPIC OR TYPE"
            elif self.menu_page == "youtube":
                heading = "YOUTUBE · favorites or type a search"
            elif self.menu_page in ("youtube_songs", "youtube_movies"):
                heading = ("FAV SONGS" if self.menu_page == "youtube_songs"
                           else "MOVIES") + " · pick one to play"
            else:
                heading = "EYE MENU"
        cv.create_text(16, 19, text=heading, fill="#d7ecff", anchor="w",
                       width=self.sw - 32, font=("Segoe UI", 15, "bold"))
        items = self.tiles()
        gap = 7
        width = (self.sw - 16 - gap*(len(items)-1)) / max(1, len(items))
        selected_index, _ = self.focused_action()
        for i, (label, _) in enumerate(items):
            x1 = 8 + i * (width + gap)
            x2 = x1 + width
            cv.create_rectangle(x1, 52, x2, 128,
                                fill="#367d99" if i == selected_index else "#294363",
                                outline="#97c8df", width=2)
            cv.create_text((x1+x2)/2, 90, text=label, fill="white", width=width - 15,
                           font=("Segoe UI", max(12, min(17, int(width / 10))), "bold"))
            if i == selected_index and self.selection == "dwell":
                cv.create_rectangle(x1, 124, x1 + width*self.dwell_progress, 128,
                                    fill="#9ef9bb", outline="")
        cv.create_polygon(self.nav.marker_x-9, 49, self.nav.marker_x+9, 49,
                          self.nav.marker_x, 38, fill="#adffd0")
        if self.mode == "assistant":
            if self.stage in ("review", "send_confirmation", "need") and self.plan:
                pages = self.review_pages()
                detail = pages[self.review_page] + \
                         (f"\nPage {self.review_page + 1}/{len(pages)}"
                          if len(pages) > 1 else "")
            elif self.stage == "done":
                detail = self.result
            elif self.stage == "ideas":
                detail = "\n".join(f"{i + 1}. {idea}"
                                   for i, idea in enumerate(self.suggestions))
            else:
                detail = "Interpreting your words. You can pause the eye input at any time."
            cv.create_text(18, 154, text=detail[:850], fill="#f1f6ff", anchor="nw",
                           width=self.sw-36, font=("Segoe UI", 12))
            hint = ("SEND delivers the message from your account · CANCEL exits"
                    if self.stage == "review" and self.plan
                    and self.assistant.can_send(self.plan) else
                    "GMAIL opens a prefilled compose · CANCEL exits"
                    if self.stage == "review" and self.plan
                    and self.plan.action == "draft_email" else
                    "GO runs the reviewed action · CANCEL exits"
                    if self.stage == "review" else
                    "SEND happens only after this separate confirmation"
                    if self.stage == "send_confirmation" else
                    "Choose EDIT to add words" if self.stage == "need" else
                    "Results appear here when the task finishes")
            cv.create_text(16, 313, text=hint, fill="#bce7c5",
                           anchor="w", font=("Segoe UI", 11))
            return
        status = ("NO FACE · MOVEMENT PAUSED" if not self.face_visible else
                  f"X-ONLY IRIS · HOLD SIDE TO REPEAT · CENTER=STOP · "
                  f"{'BLINK' if self.selection == 'blink' else 'DWELL'} TO CHOOSE · "
                  f"{'FINE' if self.precision else 'FAST'} CURSOR")
        if self.face_visible and self.mode == "keyboard" and self.selection == "blink":
            status = ("CENTER=STOP · HOLD BLINK=SELECT · DOUBLE=DELETE WORD · "
                      "TRIPLE=RUN · LONG BLINK=PAUSE"
                      if self.cfg.get("double_blink_delete", True)
                      else "CENTER=STOP · HOLD BLINK=SELECT · TRIPLE=RUN · LONG BLINK=PAUSE")
        if self.mode == "keyboard" and self.key_page == "contacts":
            total = len(self.assistant.contacts)
            status = (f"CONTACTS {self.contact_page * 5 + 1}–"
                      f"{min(total, (self.contact_page + 1) * 5)} OF {total} · "
                      f"CENTER STOPS · SELECT THE PERSON" if total else
                      "NO CONTACTS YET · IMPORT A CSV ONCE · TYPE NAME MAKES A DRAFT")
        if now < self.flash_until:
            status = self.flash
        cv.create_text(14, 150, text=status, fill="#bce7c5",
                       anchor="w", font=("Segoe UI", 11))


def main():
    try:
        IrisControl().root.mainloop()
    except (RuntimeError, ValueError, FileNotFoundError) as exc:
        print("Horizontal iris control:", exc)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
# --- END CHUNK D ---