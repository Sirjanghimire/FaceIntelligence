"""Focused checks for eye-typed request -> review -> approved action."""
import importlib
import csv
from email import policy
from email.parser import BytesParser
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import MagicMock, patch
from urllib.parse import parse_qs, urlparse

from assistant_core import Assistant, Plan
from browser_actions import BrowserActions
from horizontal_logic import FocusStepper, calibrate_horizontal
from import_contacts import import_contacts


CONFIG = json.loads((Path(__file__).parent / "config.json").read_text(encoding="utf-8"))

# Every test that touches suggestions / drafting forces the local path so
# results do not depend on whether Gemini or OpenAI is reachable.
NO_CLOUD = {"GEMINI_API_KEY": "", "GOOGLE_API_KEY": "",
            "OPENAI_API_KEY": "", "IRIS_INTENT_ENGINE": "rules"}


def _fake_control(ui, cfg=CONFIG, cal=None, **extra):
    control = ui.IrisControl.__new__(ui.IrisControl)
    control.cfg = cfg
    control.cal = cal if cal is not None else calibrate_horizontal(
        {"center": .5, "left": .42, "right": .59})
    control.cal["closed_thresholds"] = [.13, .14]
    control.selection = "blink"
    control.mode = "keyboard"
    control.menu_page = "home"
    control.key_page = "quick"
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
    control.blink = MagicMock()
    control.double_blink = MagicMock()
    control.triple_blink = MagicMock()
    control.menu_dwell = MagicMock()
    control.cursor_dwell = MagicMock()
    control.nav = FocusStepper(control.cal, control.sw, cfg, 7)
    control._gemini_lock = threading.Lock()
    control._gemini_pending = None
    control._gemini_external = None
    control._gemini_last_fragment = None
    control._gemini_last_started = 0.
    control.assistant = None
    control.root = MagicMock()
    control.bar = MagicMock()
    control.executor = MagicMock()
    for key, value in extra.items():
        setattr(control, key, value)
    return control


class AssistantPipelineTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)
        (self.root / "contacts.json").write_text(json.dumps([
            {"name": "Priya", "email": "priya@example.org", "role": "friend"},
        ]), encoding="utf-8")
        self.opened = []
        self.browser = BrowserActions(open_url=lambda url: self.opened.append(url) or True)
        self.assistant = Assistant(CONFIG, self.root, browser=self.browser)

    def test_short_eye_request_routes_to_browser_only_after_execute(self):
        for request, action in (("open YouTube", "open_youtube"),
                                ("play YouTube cat piano", "play_youtube"),
                                ("search Google for flood maps", "search_google"),
                                ("open calendar", "open_calendar")):
            with self.subTest(request=request):
                plan = self.assistant.prepare(request)
                self.assertEqual(plan.action, action)
                self.assertTrue(plan.ready)
        self.assertEqual(self.opened, [])
        plan = self.assistant.prepare("search Google for flood maps")
        self.assistant.execute(plan)
        self.assertEqual(self.opened, ["https://www.google.com/search?q=flood%20maps"])
        self.assertEqual(self.assistant.prepare("schedule on calendar").action,
                         "need_details")

    def test_youtube_fallback_does_not_claim_video_played(self):
        with patch.object(self.browser, "first_youtube_video", return_value=None):
            message = self.assistant.execute(
                self.assistant.prepare("play YouTube cat piano"))
        self.assertIn("Select a result", message)
        self.assertIn("cat%20piano", self.opened[-1])

    def test_unknown_recipient_and_incomplete_commands_never_run(self):
        for request in ("", "email Priya", "email s@m that hello", "play", "search"):
            with self.subTest(request=request):
                plan = self.assistant.prepare(request)
                self.assertFalse(plan.ready)
                with self.assertRaises(ValueError):
                    self.assistant.execute(plan)
        self.assertFalse(self.opened)

    def test_unknown_name_creates_draft_with_empty_to_and_never_enables_send(self):
        (self.root / "contacts.json").unlink()
        assistant = Assistant(CONFIG, self.root, browser=self.browser)
        with patch.dict(os.environ, {**NO_CLOUD,
                                     "SMTP_HOST": "smtp.test", "SMTP_USER": "me",
                                     "SMTP_PASSWORD": "password",
                                     "EMAIL_FROM": "me@real.test"}):
            plan = assistant.prepare("email Sam that I missed class")
            self.assertTrue(plan.ready)
            self.assertEqual(plan.contact["email"], "")
            self.assertIn("choose their address", plan.details)
            self.assertFalse(assistant.can_send(plan))
            with self.assertRaisesRegex(ValueError, "recipient address"):
                assistant.execute(plan, send=True)
            self.assertFalse((self.root / "drafts").exists())
            result = assistant.execute(plan)
            self.assertIn("Choose the recipient address", result)
            url = urlparse(self.opened[-1])
            self.assertEqual(url.hostname, "mail.google.com")
            self.assertEqual(parse_qs(url.query, keep_blank_values=True)["to"], [""])
            draft = BytesParser(policy=policy.default).parsebytes(
                next((self.root / "drafts").glob("*.eml")).read_bytes())
            self.assertIsNone(draft["To"])
            self.assertIn("I missed class", draft.get_content())

    def test_contact_suggestion_shortens_eye_typing_without_inventing_a_message(self):
        # Force the local path so this test does not depend on a cloud key.
        with patch.dict(os.environ, NO_CLOUD):
            ideas = self.assistant.suggestions("email")
            self.assertIn("email Priya that ", ideas)
            proposal = self.assistant.prepare(ideas[0])
        self.assertFalse(proposal.ready)

    def test_eye_picker_inserts_real_address_after_one_name_selection(self):
        with patch.dict(sys.modules, {"pyautogui": MagicMock(),
                                      "iris_tracking": MagicMock()}):
            ui = importlib.import_module("iris_control")
        control = _fake_control(ui)
        control.assistant = self.assistant
        control.nav = FocusStepper(control.cal, 1000, CONFIG, 9)
        control.nav.reset(9, index=0)

        ui.IrisControl.activate_key(control, "word:email")
        self.assertEqual(control.key_page, "contacts")
        self.assertEqual(control.contact_tiles()[1], ("PRIYA", "contact:0"))
        ui.IrisControl.activate_key(control, "contact:0")
        self.assertEqual(control.key_page, "main")
        self.assertEqual(control.text, "email priya@example.org that ")
        self.assertEqual(control.displayed_text(), "email Priya that ")
        control.text += "hello"
        plan = self.assistant.prepare(control.text)
        self.assertEqual(plan.contact["name"], "Priya")
        self.assertEqual(plan.contact["email"], "priya@example.org")
        self.assertFalse(self.opened)

        self.assistant.contacts.extend(
            {"name": f"Person {i}", "email": f"person{i}@real.test", "role": "contact"}
            for i in range(6))
        control.key_page, control.contact_page = "contacts", 0
        self.assertIn(("NEXT", "contact_next"), control.contact_tiles())
        ui.IrisControl.activate_key(control, "contact_next")
        self.assertEqual(control.nav.index, 0)
        self.assertIn(("PERSON 4", "contact:5"), control.contact_tiles())

    def test_local_csv_import_preserves_contacts_and_supports_export_columns(self):
        google = self.root / "google.csv"
        with google.open("w", encoding="utf-8-sig", newline="") as file:
            writer = csv.DictWriter(file, fieldnames=["Name", "E-mail 1 - Value"])
            writer.writeheader()
            writer.writerow({"Name": "Alex", "E-mail 1 - Value": "alex@real.test"})
            writer.writerow({"Name": "Other", "E-mail 1 - Value": "other@real.test"})
        self.assertEqual(import_contacts(google, self.root / "contacts.json", "Alex"),
                         (1, 2))
        self.assertEqual(import_contacts(google, self.root / "contacts.json", "Alex"),
                         (0, 2))
        outlook = self.root / "outlook.csv"
        outlook.write_text("First Name,Last Name,E-mail Address\nSam,Li,sam@real.test\n",
                           encoding="utf-8")
        self.assertEqual(import_contacts(outlook, self.root / "contacts.json"), (1, 3))
        names = [c["name"] for c in json.loads((self.root / "contacts.json").read_text())]
        self.assertEqual(names, ["Priya", "Alex", "Sam Li"])

    def test_optional_laya_choice_still_requires_review_and_confidence(self):
        self.assistant._laya = MagicMock()
        self.assistant._laya.predict.return_value = {
            "answers": {"action": {"choice": "open_calendar", "confidence": .88}}}
        with patch.dict(os.environ, {**NO_CLOUD, "IRIS_INTENT_ENGINE": "laya"}):
            plan = self.assistant.prepare("check my appointments")
            self.assertEqual((plan.action, plan.source), ("open_calendar", "laya"))
            self.assertFalse(self.opened)
            self.assistant._laya.predict.return_value["answers"]["action"]["confidence"] = .2
            self.assertFalse(self.assistant.prepare("check my appointments").ready)

    def test_email_draft_is_reviewable_and_go_never_sends(self):
        with patch.dict(os.environ, NO_CLOUD):
            plan = self.assistant.prepare("email Priya that I missed class")
        self.assertTrue(plan.ready)
        self.assertEqual(plan.contact["email"], "priya@example.org")
        self.assertIn("TO: Priya", plan.details)
        self.assertIn("SUBJECT:", plan.details)
        with patch("assistant_core.can_send", return_value=True), \
             patch("assistant_core.send_email") as send:
            result = self.assistant.execute(plan)
            self.assertIn("No email was sent", result)
            self.assertIn("Gmail compose", result)
            parsed = urlparse(self.opened[-1])
            self.assertEqual((parsed.scheme, parsed.hostname),
                             ("https", "mail.google.com"))
            fields = parse_qs(parsed.query)
            self.assertEqual(fields["to"], [plan.contact["email"]])
            self.assertEqual(fields["su"], [plan.draft["subject"]])
            self.assertEqual(fields["body"], [plan.draft["body"]])
            send.assert_not_called()
            draft = next((self.root / "drafts").glob("*.eml"))
            self.assertIn("priya@example.org", draft.read_text(encoding="utf-8"))
            self.assistant.execute(plan, send=True)
            send.assert_called_once()
            self.assertEqual(len(self.opened), 1)

    def test_gmail_compose_preserves_symbols_and_selected_account(self):
        browser = BrowserActions(open_url=lambda url: self.opened.append(url) or True,
                                 gmail_account_index=1)
        contact = {"name": "Sam", "email": "sam+iris@real.test"}
        draft = {"subject": "Hello & thank you?", "body": "Line 1\nLine 2 + 10% — café"}
        browser.compose_gmail(contact, draft)
        parsed = urlparse(self.opened[-1])
        self.assertEqual(parsed.path, "/mail/u/1/")
        params = parse_qs(parsed.query)
        self.assertEqual(params["to"], [contact["email"]])
        self.assertEqual(params["su"], [draft["subject"]])
        self.assertEqual(params["body"], [draft["body"]])
        browser.open_gmail()
        self.assertEqual(self.opened[-1], "https://mail.google.com/mail/u/1/")

    def test_browser_failure_reports_gmail_failure_and_keeps_backup(self):
        with patch.dict(os.environ, NO_CLOUD):
            plan = self.assistant.prepare("email Priya that hello")
        self.browser.open_url = lambda url: False
        with patch("assistant_core.send_email") as send:
            result = self.assistant.execute(plan)
        self.assertIn("Gmail could not be opened", result)
        self.assertIn("Backup saved", result)
        self.assertIn("No email was sent", result)
        self.assertTrue(list((self.root / "drafts").glob("*.eml")))
        send.assert_not_called()

    def test_review_pages_hide_approval_until_full_message_is_visible(self):
        with patch.dict(sys.modules, {"pyautogui": MagicMock(),
                                      "iris_tracking": MagicMock()}):
            ui = importlib.import_module("iris_control")
        control = _fake_control(ui)
        control.cfg, control.sw, control.stage = CONFIG, 1000, "review"
        control.mode, control.paused, control.selection = "assistant", False, "blink"
        control.plan = Plan("draft_email", "Email Priya",
                            details="TO: Priya\nSUBJECT: Long update\n\n" + "Status update. " * 60,
                            contact={"name": "Priya", "email": "priya@real.test"},
                            draft={"subject": "Long update", "body": "Status update. " * 60})
        control.assistant = MagicMock()
        control.assistant.can_send.return_value = True
        control.review_page = 0
        control.nav = FocusStepper(control.cal, 1000, CONFIG, 4)
        self.assertGreater(len(ui.IrisControl.review_pages(control)), 1)
        self.assertNotIn(("SEND", "request_send"),
                         ui.IrisControl.assistant_tiles(control))
        ui.IrisControl.activate_assistant(control, "go")
        control.executor.submit.assert_not_called()
        while control.review_page < len(ui.IrisControl.review_pages(control)) - 1:
            ui.IrisControl.activate_assistant(control, "next_page")
        self.assertIn(("SEND", "request_send"),
                      ui.IrisControl.assistant_tiles(control))
        ui.IrisControl.activate_assistant(control, "request_send")
        self.assertEqual(control.stage, "send_confirmation")
        self.assertNotIn(("YES, SEND", "send"),
                         ui.IrisControl.assistant_tiles(control))
        ui.IrisControl.activate_assistant(control, "send")
        control.executor.submit.assert_not_called()
        while control.review_page < len(ui.IrisControl.review_pages(control)) - 1:
            ui.IrisControl.activate_assistant(control, "next_page")
        self.assertIn(("YES, SEND", "send"),
                      ui.IrisControl.assistant_tiles(control))
        ui.IrisControl.activate_assistant(control, "send")
        self.assertEqual(control.stage, "running")
        control.executor.submit.assert_called_once()

        control.stage = "review"
        control.assistant.can_send.return_value = False
        self.assertIn(("GMAIL", "go"), ui.IrisControl.assistant_tiles(control))
        self.assertNotIn(("SEND", "request_send"),
                         ui.IrisControl.assistant_tiles(control))


if __name__ == "__main__":
    unittest.main()