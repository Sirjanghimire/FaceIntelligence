"""Eye-typed text -> explicit proposal -> approved action."""
from dataclasses import dataclass
import os
from pathlib import Path
import re

from browser_actions import BrowserActions
from jeff_agent import (can_send, draft_email, load_contacts,
                        predict_intents, save_draft, send_email)


def _cloud_key_present():
    return bool(os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
                or os.environ.get("OPENAI_API_KEY"))


@dataclass
class Plan:
    action: str
    summary: str
    details: str = ""
    target: str = ""
    contact: dict | None = None
    draft: dict | None = None
    missing: str = ""
    source: str = "rules"

    @property
    def ready(self):
        return self.action != "need_details" and not self.missing


class Assistant:
    def __init__(self, config, project_dir, browser=None):
        self.config = config
        self.project_dir = Path(project_dir)
        self.browser = browser or BrowserActions(
            gmail_account_index=config.get("gmail_account_index", 0))
        self.contacts = load_contacts(self.project_dir / "contacts.json")
        self._laya = None

    def _choice_from_laya(self, text):
        if os.environ.get("IRIS_INTENT_ENGINE",
                          self.config.get("intent_engine", "rules")) != "laya":
            return "unknown"
        try:
            if self._laya is None:
                from laya import Router
                self._laya = Router(preload=False)
            questions = {"action": {"type": "choice",
                "instructions": "Which supported computer action is requested?",
                "criteria": {
                    "play_youtube": "Find and open a requested video or song on YouTube",
                    "open_youtube": "Open YouTube without a video request",
                    "search_google": "Search the web using Google for a specified query",
                    "open_google": "Open Google without a query",
                    "open_calendar": "Open the user's calendar",
                    "open_gmail": "Open email without a recipient or message",
                    "draft_email": "Compose an email to a specified recipient",
                    "unknown": "No supported action or not enough information"}}}
            answer = self._laya.predict(text, questions)["answers"]["action"]
            if float(answer.get("confidence", 0.)) < .55:
                return "unknown"
            return answer["choice"]
        except Exception:
            return "unknown"

    @staticmethod
    def _query(text, category):
        if category == "youtube":
            match = re.search(
                r"\b(?:play|watch|search)\b(?:\s+(?:on|in))?\s*(?:youtube\b)?\s*(?:for\s+)?(.+)",
                text, re.I)
            if match:
                query = re.sub(r"\s+(?:on|in)\s+youtube\s*$", "",
                               match.group(1), flags=re.I).strip()
                return "" if query.lower() == "for" else query
            match = re.search(r"\byoutube\b\s+(.+)", text, re.I)
            query = match.group(1).strip() if match else ""
            return "" if query.lower() == "for" else query
        if re.search(r"\bgoogle\b", text, re.I):
            match = re.search(r"\bgoogle\b(?:\s+(?:for|search))?\s*(.*)", text, re.I)
            return match.group(1).strip() if match else ""
        match = re.search(r"\b(?:search|look up)\b\s*(?:for\s+)?(.*)", text, re.I)
        return match.group(1).strip() if match else ""

    def _email_plan(self, text):
        rest = re.sub(
            r"^(?:(?:send|write|compose)\s+)?(?:an?\s+)?email(?:\s+to)?\s*",
            "", text, flags=re.I).strip()
        if not rest:
            return Plan("need_details", "Who should receive the email?",
                        missing="Type: email NAME that YOUR MESSAGE")

        contact = None
        remainder = rest
        address = re.match(r"([\w.+-]+@[\w.-]+\.[A-Za-z]{2,})(?:\s+|$)", rest)
        if address:
            email = address.group(1)
            contact = next((c for c in self.contacts
                            if c["email"].casefold() == email.casefold()), None)
            if contact is None:
                contact = {"name": email.split("@")[0], "email": email,
                           "role": "contact"}
            remainder = rest[address.end():]
        else:
            for candidate in sorted(self.contacts,
                                    key=lambda c: len(c["name"]), reverse=True):
                name = candidate["name"]
                if rest.lower() == name.lower() or rest.lower().startswith(name.lower() + " "):
                    contact = candidate
                    remainder = rest[len(name):]
                    break
        if contact is None:
            unknown = re.match(
                r"(?P<name>[A-Za-z][A-Za-z .'-]{0,69}?)\s+(?:that|saying|about|to say|:|,)\s*(?P<message>.*)$",
                rest, flags=re.I)
            if unknown:
                name = unknown.group("name").strip()
                remainder = unknown.group("message")
            elif re.fullmatch(r"[A-Za-z][A-Za-z .'-]{0,69}", rest):
                name, remainder = rest, ""
            else:
                return Plan("need_details", "Enter a name or full email address.",
                            details="Try: email Alex that YOUR MESSAGE, or email alex@domain.com that YOUR MESSAGE.",
                            missing="A name or full email address is needed")
            contact = {"name": name, "email": "", "role": "address not supplied"}

        message = re.sub(r"^\s*(?:that|saying|about|to say|:|,)+\s*", "",
                         remainder, flags=re.I).strip()
        if not message:
            return Plan("need_details", "What should the email say?",
                        details="Recipient: " + contact["name"],
                        missing="Add a message after the recipient")
        draft, drafting_mode = draft_email(message, contact)
        recipient = (f"{contact['name']} <{contact['email']}>" if contact["email"]
                     else f"{contact['name']} — choose their address in Gmail before sending")
        details = (f"TO: {recipient}\nSUBJECT: {draft['subject']}\n\n"
                   f"{draft['body']}\n\nDraft: {drafting_mode}")
        return Plan("draft_email", ("Review draft for " if not contact["email"]
                                    else "Review email to ") + contact["name"],
                    details=details, contact=contact, draft=draft)

    def prepare(self, raw):
        text = " ".join(raw.strip().split())[:500]
        if not text:
            return Plan("need_details", "Choose QUICK or type a request first.",
                        missing="No command entered")
        lower = text.lower()
        if lower in ("open email", "open gmail"):
            return Plan("open_gmail", "Open Gmail")
        if re.match(r"^(?:(?:send|write|compose)\s+)?(?:an?\s+)?email\b", lower):
            return self._email_plan(text)
        if "gmail" in lower or lower == "mail":
            return Plan("open_gmail", "Open Gmail")
        if "calendar" in lower:
            if any(w in lower for w in ("create", "add", "schedule", "book")):
                return Plan("need_details", "Calendar event creation is not connected yet.",
                            details="Open Calendar to create and save the event with the eye cursor.",
                            missing="Only opening Calendar is supported")
            return Plan("open_calendar", "Open Google Calendar")
        if "youtube" in lower or re.search(r"\b(?:play|watch)\b", lower):
            query = self._query(text, "youtube")
            if re.search(r"\bsearch\b", lower) and query:
                return Plan("search_youtube", "Search YouTube for " + query, target=query)
            if query:
                return Plan("play_youtube", "Open first YouTube result for " + query,
                            details="A search result may need a manual click if YouTube changes its layout.",
                            target=query)
            if re.search(r"\b(?:play|watch|search)\b", lower):
                return Plan("need_details", "What video or song?", missing="Add a video title")
            return Plan("open_youtube", "Open YouTube")
        if "google" in lower or re.search(r"\b(?:search|look up)\b", lower):
            query = self._query(text, "google")
            if query:
                return Plan("search_google", "Search Google for " + query, target=query)
            if re.search(r"\b(?:search|look up)\b", lower):
                return Plan("need_details", "What should Google search for?",
                            missing="Add search words")
            return Plan("open_google", "Open Google")
        action = self._choice_from_laya(text)
        if action in ("play_youtube", "search_google"):
            query = self._query(text, "youtube" if action == "play_youtube" else "google") or text
            label = "YouTube" if action == "play_youtube" else "Google"
            return Plan(action, "Search " + label + " for " + query,
                        details="Laya suggested this intent. Check it before running.",
                        target=query, source="laya")
        if action in ("open_youtube", "open_google", "open_calendar", "open_gmail"):
            label = action.replace("open_", "").capitalize()
            return Plan(action, "Open " + label,
                        details="Laya suggested this intent. Check it before running.",
                        source="laya")
        return Plan("need_details", "I could not match a supported command.",
                    details="Try: open YouTube, play YouTube VIDEO, search Google for TOPIC, "
                            "open calendar, or email ADDRESS that MESSAGE.",
                    missing="Command needs editing")

    def suggestions(self, fragment):
        text = fragment.strip()[:200]
        if _cloud_key_present() and text:
            try:
                ideas = predict_intents(text, task="browser or email")
                if ideas:
                    return ideas
            except Exception:
                pass
        if not text:
            return ["open YouTube", "open calendar", "open Google"]
        lowered = text.lower()
        if "youtube" in lowered:
            return ["open YouTube", text, "search YouTube for " + self._query(text, "youtube")]
        if "calendar" in lowered:
            return ["open calendar", text]
        if "email" in lowered:
            named = [f"email {c['name']} that " for c in self.contacts
                     if lowered == "email" or c["name"].lower().startswith(
                         lowered.removeprefix("email ").split(" ")[0])]
            return list(dict.fromkeys([*named[:2], text, "open Gmail"]))[:3]
        if "google" in lowered or "search" in lowered:
            return ["open Google", text]
        return [text, "search Google for " + text]

    def can_send(self, plan):
        return (plan.action == "draft_email" and plan.contact is not None
                and bool(can_send(plan.contact)))

    def wants_auto_send(self, plan):
        """True only if the contact opted in AND SMTP is fully configured."""
        return (self.can_send(plan)
                and bool(plan.contact.get("auto_send")))


    def execute(self, plan, *, send=False):
        if not plan.ready:
            raise ValueError("This proposal needs more details")
        if plan.action == "draft_email":
            if send and not self.can_send(plan):
                raise ValueError("A full recipient address and SMTP settings are required to send")
            draft_path = save_draft(plan.contact, plan.draft,
                                    self.project_dir / "drafts")
            if send:
                send_email(plan.contact, plan.draft)
                return ("Email sent to " + plan.contact["email"] +
                        ". Draft saved: " + str(draft_path))
            try:
                result = self.browser.compose_gmail(plan.contact, plan.draft)
            except Exception as exc:
                return ("Gmail could not be opened: " + str(exc) +
                        " Backup saved: " + str(draft_path) + ". No email was sent.")
            return (result + " " +
                    ("Choose the recipient address in Gmail. "
                     if not plan.contact["email"] else "") +
                    "No email was sent by this app. Backup saved: " + str(draft_path))
        methods = {
            "open_youtube": self.browser.open_youtube,
            "play_youtube": lambda: self.browser.play_youtube(plan.target),
            "search_youtube": lambda: self.browser.search_youtube(plan.target),
            "open_google": self.browser.open_google,
            "search_google": lambda: self.browser.search_google(plan.target),
            "open_calendar": self.browser.open_calendar,
            "open_gmail": self.browser.open_gmail,
        }
        if plan.action not in methods:
            raise ValueError("Unsupported action: " + plan.action)
        return methods[plan.action]()