# Iris Assistant

A webcam-only eye-controlled desktop assistant for Windows. The system tracks **one axis of your irises** — horizontal movement only — and turns small side glances into full control of a tile-based interface at the top of the screen. Blink to select. In under a second you can open YouTube and play a favorite, run a Google search, or send an email to a saved recipient. The entire screen becomes reachable through eye movement alone; hands never leave your lap.

The project is designed for users for whom hand or head movement is unreliable or impossible, and it is built entirely on open-source components that run on the webcam already present on most laptops. It does not require dedicated eye-tracking hardware.

**What it does, in one line:** iris glances move a marker across tiles, a both-eye blink selects the tile, and the selected action — open a website, play a video, compose and send mail — is executed with an explicit review step unless the user has opted in to auto-send for a specific contact.

> **Demo recipients.** Two example recipients ship in `contacts.json` (SG and PK). They are the author's personal test addresses used during development. Replace them with your own recipients, or add entries with `import_contacts.py`, before using the email features in your environment.

---

## Table of contents

- [1. Requirements](#1-requirements)
- [2. Folder contents](#2-folder-contents)
- [3. First-time setup](#3-first-time-setup)
- [4. Calibration](#4-calibration)
- [5. Everyday use](#5-everyday-use)
- [6. Optional: auto-send email via Gmail SMTP](#6-optional-auto-send-email-via-gmail-smtp)
- [7. Optional: Gemini suggestions and drafts](#7-optional-gemini-suggestions-and-drafts)
- [8. Importing contacts from Google or Outlook](#8-importing-contacts-from-google-or-outlook)
- [9. Testing without a camera](#9-testing-without-a-camera)
- [10. Configuration reference](#10-configuration-reference)
- [11. Troubleshooting](#11-troubleshooting)
- [12. What problem this solves](#12-what-problem-this-solves)
- [13. How it differs from existing tools](#13-how-it-differs-from-existing-tools)
- [14. Known limitations](#14-known-limitations)
- [15. License and attribution](#15-license-and-attribution)

---

## 1. Requirements

- **Windows 10 or 11, 64-bit.** Tested on Windows 11.
- **Python 3.11 (64-bit)** with the Python launcher (`py`). [Download Python 3.11.9](https://www.python.org/downloads/release/python-3119/)
- A **webcam** — laptop built-in is fine. Give Windows camera permission to your terminal and to Python when prompted.
- **Internet connection** for YouTube, Google, Gmail, and (optionally) Gemini.
- A modern default browser signed into the Gmail account you want to use.

First run installs about 800 MB (Playwright Chromium is the largest piece) and takes roughly 5 minutes.

---

## 2. Folder contents
iris_assistant/
├── README.md This file
├── run.bat One-command setup and launch
├── run_laya.bat Same, with the optional Laya classifier
├── requirements.txt Core dependencies
├── requirements-laya.txt Optional Laya dependency
├── config.json Speeds, blink timing, topics, quick words
├── calibration.json Created locally after first calibration
├── contacts.json Recipients (name, email, role, optional auto_send)
├── contacts.example.json Format reference
├── contacts.example.csv CSV import format reference
├── favorites.json YouTube songs and movies shown as tiles
├── calibrate.py Webcam + blink calibration
├── iris_tracking.py Camera loop, iris X and eyelid openness only
├── horizontal_logic.py Cursor, focus stepper, blink detectors, keyboard
├── iris_control.py The app: top bar, home screen, keyboard, review
├── assistant_core.py Request parsing and Plan objects
├── jeff_agent.py Gemini/OpenAI integration, email drafting, SMTP
├── browser_actions.py YouTube, Google, Calendar, Gmail compose
├── assistant_cli.py Camera-free command preview
├── import_contacts.py One-time local CSV importer
├── test_horizontal_logic.py Unit tests for eye control logic
├── test_iris_tracking.py Unit tests for the background camera worker
└── test_assistant.py Unit tests for the assistant and approval flow

drafts/ Auto-created; every reviewed email saved as .eml
.venv/ Auto-created by run.bat

text

> **Never commit** `calibration.json`, `contacts.json`, or `drafts/` to a public repository. They contain personal data. See `.gitignore`.

---

## 3. First-time setup

Open **Command Prompt** inside the folder:

```bat
cd C:\Users\<you>\Downloads\iris_assistant
Then run:

bat
py -3.11 --version
run.bat
run.bat on first run:

Creates .venv/ (a private Python environment for this project).

Installs the packages in requirements.txt.

Tries to install Playwright Chromium (optional — enables direct YouTube video opening; without it, play YouTube ... opens search results).

Launches calibrate.py and shows CENTER, LEFT, RIGHT, then CLOSE BOTH EYES. Follow each with your eyes only; keep your head still.

Saves calibration.json and launches the app.

Later runs skip steps 1–4 and jump straight into the app.

If the wrong camera is picked: open config.json, change "camera_index" to 1, delete calibration.json, and run run.bat again.

4. Calibration
Calibration is the single most important step. If it's wrong, nothing works.

To redo calibration:

bat
.venv\Scripts\activate
python calibrate.py
Follow the on-screen dots. Full calibration takes about 15 seconds.

What it measures:

Where your irises sit when you look at the center of the screen.

How far they move when you look left and right.

How closed your eyelids get during a deliberate blink vs. a natural one. If this step is unreliable, the app automatically switches to dwell selection — you hold your gaze on a tile for 0.85 s instead of blinking.

Tips:

Even, front-facing light. Avoid a window behind you.

Sit roughly arm's length from the screen.

Move only your eyes during calibration, not your head.

If it says "Horizontal iris signal is too weak", move closer and increase light on both eyes.

Re-center without a full calibration: from the app, CURSOR → RE-CENTER.

5. Everyday use
5.1 Moving the marker
The green triangle at the top sits above the focused tile. Look left or right to move it. Look at screen center to stop. Hold a side glance to step repeatedly. Small accidental glances do nothing.

5.2 Selecting a tile
Two modes:

Blink mode (default when calibration succeeds). Hold both eyes closed for 0.4–0.8 seconds, then open.

Dwell mode (automatic fallback). Look steadily at a tile; a green bar fills after ~0.85 s.

The bottom-left status line tells you which mode is active.

5.3 Home screen
Tile	Action
EMAIL	Opens the recipient picker
YOUTUBE	Opens FAV SONGS · MOVIES · TYPE
GOOGLE	Opens google.com in your browser
ALPHABETS	Opens the on-screen keyboard
UNDO	Restores the last text deletion
RUN	Sends the current text to the assistant
CURSOR	Desktop cursor, click, scroll, paste, fine movement, safe mode, re-center
5.4 Typing
Select ALPHABETS. The keyboard has:

Two predicted next-word tiles (Gemini if configured, local otherwise).

Letter groups A–F, G–L, M–R, S–X, Y/Z.

0–9 for digits, SYM for punctuation.

SPACE, DEL, RUN, QUICK, BACK.

Gestures while typing:

Double-blink deletes the last word.

Triple-blink anywhere triggers RUN.

Long blink (~1.7 s) pauses everything.

5.5 Sending email
Default flow (review required):

EMAIL → pick a contact (e.g. SG).

Choose a topic (EMERGENCY · FOOD · WELLBEING · CHECK IN · CONTACT ME) or TYPE your own.

Gemini drafts the message (local template if Gemini unavailable).

Read the draft, page through if long.

Select GMAIL. Browser opens a prefilled compose. Click Send in Gmail.

A copy of every reviewed message is saved to drafts/ as .eml.

Auto-send flow (opt-in per contact):

If a contact in contacts.json has "auto_send": true and SMTP is configured (§6), then after you pick a topic the message is sent immediately. No review screen and no undo. Only mark contacts auto_send: true if you accept that.

5.6 YouTube
Select YOUTUBE, then:

FAV SONGS → pick a saved song. Edit favorites.json to change the list.

MOVIES → same for movies.

TYPE → opens the keyboard with play YouTube prefilled.

5.7 Desktop cursor
Select CURSOR:

Tile	Action
MOVE X	Look left/right to slide the cursor horizontally
MOVE Y	Left glance = up, right glance = down
CLICK	Left-click at the current position
R-CLICK	Right-click
SCROLL ↑ / ↓	Scroll the focused window
PASTE	Paste the clipboard into the focused app
FINE / FAST	Toggle precision cursor speed
RE-CENTER	Recalibrate the iris neutral point
SAFE / UNSAFE	Toggle safe mode — blocks all desktop actions
BACK	Return to the home screen
Esc on the physical keyboard exits the app.

6. Optional: auto-send email via Gmail SMTP
Skip this section if you want review-before-send. The default Gmail-compose flow works without any configuration.

To deliver email directly — necessary for auto_send: true contacts — you need a Gmail App Password and five environment variables.

6.1 Create the App Password
Sign in to the sending account at https://myaccount.google.com/apppasswords

If the page says "not available", turn on 2-Step Verification at https://myaccount.google.com/security first, then return.

Type a name (e.g. iris) and click Create.

Google shows a 16-character code with spaces, like abcd efgh ijkl mnop. Remove the spaces → abcdefghijklmnop.

6.2 Set the environment variables
In the same Command Prompt where you launch the app:

bat
set "SMTP_HOST=smtp.gmail.com"
set "SMTP_PORT=587"
set "SMTP_USER=you@gmail.com"
set "SMTP_PASSWORD=abcdefghijklmnop"
set "EMAIL_FROM=you@gmail.com"
run.bat
Verify all five:

bat
echo %SMTP_HOST% %SMTP_PORT% %SMTP_USER% %SMTP_PASSWORD% %EMAIL_FROM%
set only lasts for that window. To make them permanent:

bat
setx SMTP_HOST "smtp.gmail.com"
setx SMTP_PORT "587"
setx SMTP_USER "you@gmail.com"
setx SMTP_PASSWORD "abcdefghijklmnop"
setx EMAIL_FROM "you@gmail.com"
Then close and reopen the Command Prompt.

6.3 Common SMTP failures
Error	Fix
535 Authentication failed	You used your normal password, not an App Password, or you left spaces in it. Regenerate and set again with no spaces.
534 Application-specific password required	You need an App Password, and 2-Step Verification must be on.
Connection refused / timeout	Your network blocks outbound port 587. Try 465, or a different network.
SEND tile never appears	One of the five variables isn't set, or the recipient address is a placeholder. Re-run the echo check.
7. Optional: Gemini suggestions and drafts
Gemini is used for:

Next-word suggestions while typing (background, debounced; local predictions show instantly).

Intent suggestions on the IDEAS screen.

Email drafts when you pick a topic or type a request.

Without Gemini, the app uses bundled local suggestions and email templates. Nothing crashes.

Enable:

bat
set "GEMINI_API_KEY=your-api-key-here"
set "GEMINI_MODEL=gemini-2.0-flash"
run.bat
Get a key at https://aistudio.google.com/apikey.

Permanent:

bat
setx GEMINI_API_KEY "your-api-key-here"
setx GEMINI_MODEL "gemini-2.0-flash"
If Gemini is unavailable — bad key, network block, quota exceeded — every feature falls back silently. Drafts show Draft: Local template instead of Draft: Gemini draft.

Optional OpenAI fallback: if OPENAI_API_KEY is also set, the code tries Gemini first, then OpenAI, then local.

8. Importing contacts from Google or Outlook
Export contacts to CSV:

Google Contacts export

Outlook contacts export

From the project folder:

bat
.venv\Scripts\activate
python import_contacts.py "%USERPROFILE%\Downloads\contacts.csv" --names "Sam,Priya"
--names imports only people whose name contains one of the fragments; omit it to import everyone.

9. Testing without a camera
bat
.venv\Scripts\activate
python assistant_cli.py play YouTube cat piano
python assistant_cli.py "email Sam that I missed class"
python assistant_cli.py "search Google for flood maps" --execute
--execute opens browser actions; for email it opens Gmail compose and saves an .eml. It never sends via SMTP.

Run the unit tests:

bat
python -m unittest -v test_horizontal_logic test_assistant test_iris_tracking
All 36 tests should pass. None need a webcam.

10. Configuration reference
config.json — restart run.bat after edits.

Key	Meaning
camera_index	Which webcam. 0 is usually the built-in.
selection_mode	"auto", "blink", or "dwell".
nav_trigger	How far sideways before the marker moves. Higher = less twitchy.
nav_hold_s	How long to hold a side glance before the first step.
nav_repeat_s	Interval between auto-repeats while holding.
deadzone	How much iris movement is ignored as jitter.
speed_x, speed_y	Desktop cursor speed.
long_blink_min_s / long_blink_max_s	Selection blink window.
pause_blink_min_s / pause_blink_max_s	Pause toggle window.
double_blink_*	Word-delete gesture tuning.
triple_blink_run	Whether triple-blink triggers RUN.
email_topics	Topic buttons shown after picking a recipient.
quick_words	Six shortcut words on the keyboard's QUICK page.
gmail_account_index	Which signed-in Gmail account for compose.
11. Troubleshooting
Problem	Fix
App exits immediately with a traceback	Paste the traceback. Most common cause: a file wasn't overwritten with the current version.
"Camera unavailable"	Close other apps using the camera (Teams, Zoom). Check camera_index.
Marker jumps several tiles	Re-run calibrate.py. Lighting or seating changed.
Marker never moves	Iris signal weak. Move closer, increase light.
Marker moves but won't select	Blink too fast or too slow. Count "one-Mississippi".
Double-blink deletes unintended words	Set "double_blink_delete": false in config.json.
YOUTUBE tile just types the word youtube	You're on the keyboard, not the home screen. The home YOUTUBE opens the submenu; the YOUTUBE quick word inserts the literal text.
GMAIL tile doesn't appear after reviewing an email	SMTP is configured → the tile is SEND. Otherwise the tile is GMAIL.
Email doesn't send	535 errors mean wrong App Password. See §6.3.
Gemini drafts look identical to old messages	Gemini call failed, local template used. Check terminal for 401 / 403.
Playwright Chromium install fails	Harmless. play YouTube ... falls back to search results.
12. What problem this solves
Standard assistive input devices require either hand movement (mouse, joystick, switch) or head tracking (large head-mounted sensors). For users with severe motor impairment, both are tiring or impossible. Eye gaze is the last reliable motor channel, but most gaze-tracking systems are expensive dedicated hardware.

This project explores a different point in the design space:

It uses a webcam you already own — no special hardware.

It tracks only one axis (horizontal iris position), which is achievable with open-source MediaPipe landmarks at full framerate on a laptop CPU. Vertical iris motion is noisier and less repeatable across users, so the project deliberately reuses the horizontal signal for both axes.

It provides very large targets (top-of-screen tiles) sized to be hit reliably with one-axis movement, rather than a free-floating pointer.

It treats every action as a reviewable proposal unless the user explicitly opts in to auto-send per contact.

It is entirely local and offline-capable for the core flow. Only Gmail and (optionally) Gemini require internet.

13. How it differs from existing tools
Existing approach	This project
Dedicated eye-tracking hardware (Tobii, EyeTech) costing hundreds to thousands	Runs on any Windows laptop with a webcam
Two-axis iris tracking requiring careful calibration to a screen	Single-axis iris signal, reused for both axes; faster to calibrate, less sensitive to head pose
Dwell-only selection (tiring on the eyes)	Blink selection by default; dwell is an automatic fallback
Voice-first assistants (Siri, Alexa) that assume speech is available	Silent by design; no voice required
Full OCR or on-screen keyboard agents that move the OS cursor everywhere	A dedicated tile interface sized for the input method; desktop cursor is one option, not the only one
Cloud-first AI that sends your typed text to a server	Local by default; Gemini or OpenAI only if you opt in
Auto-send everything to maximize convenience	Review by default; auto-send is opt-in per contact
14. Known limitations
One-axis iris tracking is inherently less precise than dedicated two-axis eye trackers. Fine work (image editing, code) is not the target use case.

Vertical cursor motion reuses horizontal eye movement. It is controllable but not intuitive for first-time users.

Blink-based selection depends on reliable eyelid tracking. Users who wear thick glasses, or sit in poor lighting, may need dwell mode.

Auto-send has no undo. Once a message leaves via SMTP, it is delivered.

Gmail compose opens the account specified by gmail_account_index. With multiple signed-in Google accounts, verify which one is active before clicking Send.

The Gemini integration depends on a third-party API. If it becomes unavailable, the app falls back to local templates and suggestions automatically.

15. License and attribution
Provided as-is for educational and personal use. Uses:

MediaPipe (Apache 2.0) — face landmark detection

OpenCV (Apache 2.0) — camera input

PyAutoGUI (BSD) — cursor and keyboard control

Playwright (Apache 2.0) — optional YouTube result extraction

Tkinter (PSF) — the interface

Gemini and OpenAI integration are optional and governed by their own terms.
