"""Small, review-first task agent. Cloud drafting is optional; send is explicit."""

import json
import os
import re
import smtplib
import urllib.request
from email.message import EmailMessage
from pathlib import Path


SUGGESTIONS = [
    "Email professor about missing class",
    "Email professor to request a meeting",
    "Email a friend about Friday",
    "Thank someone for their help",
    "Ask for a copy of the notes",
    "Tell my family I am doing well",
    "Ask to reschedule our meeting",
    "Reply that Friday works for me",
]


def suggested_intents(fragment):
    words = re.findall(r"[\w']+", fragment.lower())
    ranked = sorted(SUGGESTIONS, key=lambda s: (
        -sum(w in s.lower() for w in words), len(s))) if words else SUGGESTIONS
    return [s for s in ranked if s.lower() != fragment.strip().lower()][:3]


def load_contacts(path):
    path = Path(path)
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        entries = json.load(f)
    if not isinstance(entries, list):
        raise ValueError("contacts.json must be a list of objects")
    return [c for c in entries if isinstance(c, dict) and
            all(isinstance(c.get(k), str) for k in ("name", "email", "role"))]


def suggest_contacts(fragment, contacts):
    words = re.findall(r"[\w']+", fragment.lower())
    return sorted(contacts, key=lambda c: -sum(
        w in (c["name"] + " " + c["role"]).lower() for w in words))[:4]


# --- Gemini ---------------------------------------------------------------

GEMINI_ENDPOINT = ("https://generativelanguage.googleapis.com/v1beta/models/"
                   "{model}:generateContent")


def _gemini_key():
    return os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")


def _gemini_json(instructions, user_input, schema, max_tokens=400):
    key = _gemini_key()
    if not key:
        raise ValueError("GEMINI_API_KEY is not set")
    model = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash")
    payload = {
        "system_instruction": {"parts": [{"text": instructions}]},
        "contents": [{"role": "user", "parts": [{"text": user_input}]}],
        "generationConfig": {
            "responseMimeType": "application/json",
            "responseSchema": schema,
            "maxOutputTokens": max_tokens,
            "temperature": 0.4,
        },
    }
    req = urllib.request.Request(
        GEMINI_ENDPOINT.format(model=model) + "?key=" + key,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST")
    with urllib.request.urlopen(req, timeout=18) as response:
        data = json.load(response)
    try:
        text = data["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError):
        raise ValueError("Gemini returned no text")
    return json.loads(text)


# --- OpenAI (optional fallback) ------------------------------------------

def _llm_json(instructions, user_input, schema, name, max_tokens=400):
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        raise ValueError("OPENAI_API_KEY is not set")
    payload = {
        "model": os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
        "instructions": instructions,
        "input": user_input,
        "text": {"format": {"type": "json_schema", "name": name,
                            "strict": True, "schema": schema}},
        "max_output_tokens": max_tokens,
    }
    req = urllib.request.Request(
        "https://api.openai.com/v1/responses",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": "Bearer " + key},
        method="POST")
    with urllib.request.urlopen(req, timeout=18) as response:
        data = json.load(response)
    for item in data.get("output", []):
        if item.get("type") == "message":
            for content in item.get("content", []):
                if content.get("type") == "output_text":
                    return json.loads(content["text"])
    raise ValueError("The drafting service did not return a result")


# --- Intent suggestions ---------------------------------------------------

INTENT_SCHEMA = {"type": "object", "properties": {
    "suggestions": {"type": "array", "items": {"type": "string"}}},
    "required": ["suggestions"], "additionalProperties": False}
INTENT_INSTRUCTIONS = (
    "Complete the user's incomplete intention for an assistive eye keyboard. "
    "Give exactly three DISTINCT short possible complete intentions, each under 60 characters. "
    "Preserve the given words and do not invent a person's name, reason, date, or promise. "
    "These are suggestions, not decisions. Do not add explanations.")


def predict_intents(fragment, task="email"):
    prompt = f"Task: {task}\nWords entered: {fragment}"
    if _gemini_key():
        try:
            result = _gemini_json(INTENT_INSTRUCTIONS, prompt, INTENT_SCHEMA, 220)
            options = result.get("suggestions", [])
            cleaned = [s.strip() for s in options if isinstance(s, str) and s.strip()][:3]
            if cleaned:
                return cleaned
        except Exception:
            pass
    if os.environ.get("OPENAI_API_KEY"):
        try:
            result = _llm_json(INTENT_INSTRUCTIONS, prompt, INTENT_SCHEMA,
                               "intent_suggestions", 220)
            options = result.get("suggestions", [])
            cleaned = [s.strip() for s in options if isinstance(s, str) and s.strip()][:3]
            if cleaned:
                return cleaned
        except Exception:
            pass
    return suggested_intents(fragment)


# --- Next-word predictions ------------------------------------------------

WORD_SCHEMA = {"type": "object", "properties": {
    "words": {"type": "array", "items": {"type": "string"}}},
    "required": ["words"], "additionalProperties": False}
WORD_INSTRUCTIONS = (
    "The user is typing a short command or message with an eye keyboard. "
    "Suggest exactly three likely NEXT single words (no spaces, no punctuation, "
    "lowercase) that would sensibly continue the text. Do not repeat the "
    "partial word being typed unless completing it. Do not invent names, "
    "dates, or facts. Output only the JSON object.")


def predict_words_remote(text, limit=3):
    fragment = (text or "").strip()[-120:]
    if not fragment:
        return []
    prompt = f"Text so far: {fragment!r}"
    if _gemini_key():
        try:
            result = _gemini_json(WORD_INSTRUCTIONS, prompt, WORD_SCHEMA, 80)
            words = result.get("words", [])
            cleaned = [w.strip().lower() for w in words
                       if isinstance(w, str) and w.strip() and " " not in w.strip()][:limit]
            if cleaned:
                return cleaned
        except Exception:
            pass
    if os.environ.get("OPENAI_API_KEY"):
        try:
            result = _llm_json(WORD_INSTRUCTIONS, prompt, WORD_SCHEMA,
                               "word_suggestions", 80)
            words = result.get("words", [])
            cleaned = [w.strip().lower() for w in words
                       if isinstance(w, str) and w.strip() and " " not in w.strip()][:limit]
            if cleaned:
                return cleaned
        except Exception:
            pass
    return []


# --- Email drafting -------------------------------------------------------

DRAFT_SCHEMA = {"type": "object", "properties": {
    "subject": {"type": "string"}, "body": {"type": "string"}},
    "required": ["subject", "body"], "additionalProperties": False}
DRAFT_INSTRUCTIONS = (
    "Draft a concise respectful email in the user's voice, at most 65 words. "
    "Do not invent reasons, dates, promises or other facts. "
    "If intent is ambiguous, keep the body general. Do not add a signature.")


def _gemini_draft(intent, contact):
    draft = _gemini_json(
        DRAFT_INSTRUCTIONS,
        f"User's eye-typed intention: {intent}\nRecipient: {contact['name']} ({contact['role']})",
        DRAFT_SCHEMA, 250)
    if all(isinstance(draft.get(k), str) and draft[k].strip() for k in ("subject", "body")):
        return draft
    raise ValueError("Gemini did not return an email")


def _llm_draft(intent, contact):
    draft = _llm_json(
        DRAFT_INSTRUCTIONS,
        f"User's eye-typed intention: {intent}\nRecipient: {contact['name']} ({contact['role']})",
        DRAFT_SCHEMA, "email_draft", 250)
    if all(isinstance(draft.get(k), str) and draft[k].strip() for k in ("subject", "body")):
        return draft
    raise ValueError("The drafting service did not return an email")


def draft_email(intent, contact):
    if not intent.strip():
        raise ValueError("Enter an intention first")
    if _gemini_key():
        try:
            return _gemini_draft(intent, contact), "Gemini draft"
        except Exception:
            pass
    if os.environ.get("OPENAI_API_KEY"):
        try:
            return _llm_draft(intent, contact), "AI draft"
        except Exception:
            pass
    description = intent.strip().rstrip(".?!")
    if "miss" in description.lower() and "class" in description.lower():
        subject = "Following up about class"
        body = "I missed class. Could you please let me know what I should review?"
    elif "meeting" in description.lower():
        subject = "Meeting request"
        body = "Could we schedule a meeting? Please let me know a time that works for you."
    else:
        subject = description[:70].capitalize()
        body = f"I'm writing regarding: {description}. Please let me know your thoughts."
    return {"subject": subject,
            "body": f"Hello {contact['name']},\n\n{body}\n\nThank you."}, \
        "Local template"


def _message(contact, draft, sender=None):
    recipient = contact.get("email", "")
    if recipient and not re.fullmatch(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", recipient):
        raise ValueError("Invalid recipient email")
    if sender and not recipient:
        raise ValueError("A recipient email is required to send")
    message = EmailMessage()
    if recipient:
        message["To"] = recipient
    if sender:
        message["From"] = sender
    message["Subject"] = draft["subject"].replace("\n", " ").replace("\r", " ")
    message.set_content(draft["body"])
    return message


def save_draft(contact, draft, folder):
    path = Path(folder)
    path.mkdir(parents=True, exist_ok=True)
    import datetime
    import uuid
    filename = path / (datetime.datetime.now().strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:6] + ".eml")
    filename.write_bytes(_message(contact, draft).as_bytes())
    return filename


def can_send(contact):
    return all(os.environ.get(k) for k in ("SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD", "EMAIL_FROM")) and \
           bool(re.fullmatch(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", contact.get("email", ""))) and \
           not contact["email"].lower().endswith(("@example.com", "@example.org", "@example.net"))


def send_email(contact, draft):
    if not can_send(contact):
        raise ValueError("Configure SMTP and select a real recipient to send")
    msg = _message(contact, draft, os.environ["EMAIL_FROM"])
    with smtplib.SMTP(os.environ["SMTP_HOST"], int(os.environ.get("SMTP_PORT", "587")), timeout=20) as smtp:
        smtp.starttls()
        smtp.login(os.environ["SMTP_USER"], os.environ["SMTP_PASSWORD"])
        smtp.send_message(msg)