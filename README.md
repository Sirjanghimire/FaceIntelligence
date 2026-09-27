# Iris Assistant

**Iris Assistant** is a webcam-only, eye-controlled desktop assistant for Windows.

The system tracks **one axis of your irises — horizontal movement only** — and converts small side glances into control of a tile-based interface positioned at the top of the screen.

Look left or right to move between tiles. Blink to select.

With only eye movement, a user can:

- Open YouTube and play saved favorites
- Search Google
- Compose and send emails
- Type using an on-screen keyboard
- Control the Windows cursor
- Click, scroll, paste, and navigate desktop applications

The system is designed for users for whom **hand or head movement is unreliable, difficult, or impossible**.

It uses open-source components and works with the webcam already built into most laptops. **No dedicated eye-tracking hardware is required.**

---

## How It Works

> **In one line:** Iris glances move a marker across large interface tiles, a both-eye blink selects the focused tile, and the selected action is executed with an explicit review step unless the user has intentionally enabled auto-send for a specific email contact.

The system deliberately tracks only **horizontal iris movement**.

Horizontal movement is generally more stable with ordinary webcams than vertical gaze estimation. The same horizontal signal can therefore be reused for different interaction modes, including vertical cursor control.

---

## Demo Recipients

Two example recipients are included in `contacts.json`:

- `SG`
- `PK`

These are personal test addresses used during development.

Before using the email features, replace them with your own contacts or import contacts using `import_contacts.py`.

> **Privacy note:** Never upload your personal `contacts.json`, `calibration.json`, or generated email drafts to a public repository.

---

## Table of Contents

1. [Requirements](#1-requirements)
2. [Folder Structure](#2-folder-structure)
3. [First-Time Setup](#3-first-time-setup)
4. [Calibration](#4-calibration)
5. [Everyday Use](#5-everyday-use)
6. [Optional: Gmail SMTP Auto-Send](#6-optional-gmail-smtp-auto-send)
7. [Optional: Gemini Suggestions and Drafts](#7-optional-gemini-suggestions-and-drafts)
8. [Importing Contacts](#8-importing-contacts)
9. [Testing Without a Camera](#9-testing-without-a-camera)
10. [Configuration Reference](#10-configuration-reference)
11. [Troubleshooting](#11-troubleshooting)
12. [What Problem This Solves](#12-what-problem-this-solves)
13. [How It Differs From Existing Tools](#13-how-it-differs-from-existing-tools)
14. [Known Limitations](#14-known-limitations)
15. [License and Attribution](#15-license-and-attribution)

---

# 1. Requirements

### Operating System

- **Windows 10 or Windows 11**
- 64-bit system
- Tested primarily on Windows 11

### Python

Install:

**Python 3.11, 64-bit**

The Python launcher command `py` should also be available.

Download Python 3.11.9:

https://www.python.org/downloads/release/python-3119/

Verify the installation:

```bat
py -3.11 --version
```

### Webcam

A standard webcam is required.

A laptop's built-in webcam is sufficient.

Make sure Windows allows camera access for:

- Python
- Command Prompt / Terminal
- Desktop applications

### Internet Connection

Internet access is required for features such as:

- YouTube
- Google Search
- Gmail
- Gemini
- OpenAI fallback

The core interface and local fallback logic can still operate without cloud AI services.

### Browser

A modern default browser is recommended.

For Gmail features, sign into the Gmail account you want Iris Assistant to use.

---

## First-Run Download Size

The first installation may download approximately **800 MB** of dependencies.

The largest component is usually Playwright Chromium.

Installation time depends on your internet connection.

---

# 2. Folder Structure

```text
iris_assistant/
│
├── README.md
├── run.bat
├── run_laya.bat
├── requirements.txt
├── requirements-laya.txt
│
├── config.json
├── calibration.json
├── contacts.json
├── contacts.example.json
├── contacts.example.csv
├── favorites.json
│
├── calibrate.py
├── iris_tracking.py
├── horizontal_logic.py
├── iris_control.py
├── assistant_core.py
├── jeff_agent.py
├── browser_actions.py
├── assistant_cli.py
├── import_contacts.py
│
├── test_horizontal_logic.py
├── test_iris_tracking.py
├── test_assistant.py
│
├── drafts/
└── .venv/
```

### Main Files

| File | Purpose |
|---|---|
| `README.md` | Project documentation |
| `run.bat` | One-command setup and launch |
| `run_laya.bat` | Launches with the optional Laya classifier |
| `requirements.txt` | Core Python dependencies |
| `requirements-laya.txt` | Optional Laya dependencies |
| `config.json` | Navigation speeds, blink timing, topics, quick words, and other settings |
| `calibration.json` | Generated locally after calibration |
| `contacts.json` | Saved email recipients |
| `contacts.example.json` | Example contact format |
| `contacts.example.csv` | Example CSV import format |
| `favorites.json` | Saved YouTube songs and movies |
| `calibrate.py` | Webcam and blink calibration |
| `iris_tracking.py` | Camera loop and iris/eyelid tracking |
| `horizontal_logic.py` | Navigation, blink detection, and cursor logic |
| `iris_control.py` | Main graphical application |
| `assistant_core.py` | Request parsing and assistant plan objects |
| `jeff_agent.py` | Gemini/OpenAI integration, email drafting, and SMTP |
| `browser_actions.py` | YouTube, Google, Gmail, and browser actions |
| `assistant_cli.py` | Camera-free command preview |
| `import_contacts.py` | Local CSV contact importer |
| `test_horizontal_logic.py` | Unit tests for eye-control logic |
| `test_iris_tracking.py` | Unit tests for the camera worker |
| `test_assistant.py` | Assistant and approval-flow tests |
| `drafts/` | Automatically created folder containing reviewed `.eml` drafts |
| `.venv/` | Automatically created Python virtual environment |

---

## Files That Should Never Be Committed

Do **not** commit the following to a public repository:

```text
calibration.json
contacts.json
drafts/
.venv/
```

These files may contain:

- Personal contact information
- Calibration data
- Email content
- Locally generated application data

Add them to `.gitignore`.

Example:

```gitignore
.venv/
calibration.json
contacts.json
drafts/
__pycache__/
*.pyc
.env
```

---

# 3. First-Time Setup

Open **Command Prompt** inside the project folder.

Example:

```bat
cd C:\Users\<your-username>\Downloads\iris_assistant
```

Verify Python:

```bat
py -3.11 --version
```

Then run:

```bat
run.bat
```

---

## What `run.bat` Does

On the first run, the script:

1. Creates a private Python virtual environment:

```text
.venv/
```

2. Installs the dependencies listed in:

```text
requirements.txt
```

3. Attempts to install Playwright Chromium.

Playwright is optional but enables more direct YouTube navigation.

If Playwright is unavailable, commands such as:

```text
play YouTube ...
```

fall back to opening YouTube search results.

4. Launches `calibrate.py`.

5. Guides the user through:

```text
CENTER
LEFT
RIGHT
CLOSE BOTH EYES
```

6. Saves the result as:

```text
calibration.json
```

7. Launches Iris Assistant.

---

## Later Runs

After the environment and calibration file already exist, running:

```bat
run.bat
```

skips most installation steps and launches the application directly.

---

## Wrong Camera Selected

If Iris Assistant opens the wrong webcam, edit:

```text
config.json
```

Change:

```json
"camera_index": 0
```

to:

```json
"camera_index": 1
```

Then delete:

```text
calibration.json
```

and run:

```bat
run.bat
```

again.

---

# 4. Calibration

Calibration is one of the most important parts of the system.

Poor calibration can cause:

- Incorrect navigation
- Excessive marker movement
- No movement
- Missed blinks
- Accidental selections

To recalibrate manually:

```bat
.venv\Scripts\activate
python calibrate.py
```

Follow the on-screen targets.

Typical calibration takes approximately **15 seconds**.

---

## What Calibration Measures

The calibration process estimates:

### Neutral Iris Position

Where the user's irises sit while looking at the center of the display.

### Left and Right Range

How far the iris moves when looking:

- Left
- Center
- Right

### Eyelid Closure

How closed the eyelids become during an intentional selection blink compared with ordinary blinking.

If blink detection is unreliable, Iris Assistant can automatically fall back to **dwell selection**.

---

## Calibration Tips

For best results:

- Use even, front-facing lighting.
- Avoid bright windows directly behind you.
- Sit roughly an arm's length from the display.
- Keep your head relatively still.
- Move your eyes rather than your entire head.
- Make sure both eyes are clearly visible.
- Avoid extremely dark environments.

If the application reports:

```text
Horizontal iris signal is too weak
```

try:

- Moving closer to the webcam
- Increasing light on your face
- Removing strong glare from glasses
- Looking farther left and right during calibration

---

## Re-Center Without Full Calibration

If the neutral eye position has shifted slightly during use:

```text
CURSOR → RE-CENTER
```

This adjusts the neutral position without requiring a full calibration.

---

# 5. Everyday Use

# 5.1 Moving the Marker

A marker at the top of the interface indicates the currently focused tile.

Look:

- **Left** to move left
- **Right** to move right
- **Center** to stop

Holding a side glance causes repeated movement after a short delay.

Small accidental eye movements inside the configured dead zone are ignored.

---

# 5.2 Selecting a Tile

Iris Assistant supports two selection modes.

## Blink Mode

Blink mode is preferred when calibration succeeds.

To select a tile:

1. Focus the desired tile.
2. Close both eyes deliberately.
3. Hold the blink for approximately **0.4–0.8 seconds**.
4. Open your eyes.

The selected tile is activated.

---

## Dwell Mode

If blink tracking is unreliable, the application can switch to dwell mode.

To select:

1. Focus a tile.
2. Keep the marker on the tile.
3. Hold your gaze for approximately **0.85 seconds**.

A progress indicator fills before activation.

The application status area indicates which selection mode is currently active.

---

# 5.3 Home Screen

The main screen provides several large tiles.

| Tile | Action |
|---|---|
| `EMAIL` | Opens the saved recipient picker |
| `YOUTUBE` | Opens favorite songs, movies, or typed YouTube search |
| `GOOGLE` | Opens Google |
| `ALPHABETS` | Opens the on-screen keyboard |
| `UNDO` | Restores the most recently deleted text |
| `RUN` | Sends the current text to the assistant |
| `CURSOR` | Opens desktop cursor controls |

---

# 5.4 On-Screen Keyboard

Select:

```text
ALPHABETS
```

to open the keyboard.

The keyboard contains:

### Predictive Tiles

Two predicted next-word suggestions are displayed.

If Gemini is configured, suggestions may use Gemini.

Otherwise, local prediction logic is used.

### Letter Groups

Letters are grouped into large tiles:

```text
A–F
G–L
M–R
S–X
Y/Z
```

### Numbers

```text
0–9
```

### Symbols

Select:

```text
SYM
```

for punctuation and symbols.

### Other Controls

```text
SPACE
DEL
RUN
QUICK
BACK
```

---

## Keyboard Blink Gestures

### Double Blink

Deletes the last word.

This can be disabled in `config.json`.

### Triple Blink

Triggers:

```text
RUN
```

from anywhere when enabled.

### Long Blink

A blink of approximately **1.7 seconds** pauses or resumes eye-control input.

---

# 5.5 Sending Email

Iris Assistant supports two email workflows.

---

## Default Email Flow: Review Required

The normal workflow is:

```text
EMAIL
→ Choose Contact
→ Choose Topic
→ Review Draft
→ GMAIL
→ Send
```

Example contacts:

```text
SG
PK
```

Available topic tiles may include:

```text
EMERGENCY
FOOD
WELLBEING
CHECK IN
CONTACT ME
TYPE
```

After selecting a topic:

1. Gemini attempts to generate a draft.
2. If Gemini is unavailable, a local template is used.
3. The user reviews the message.
4. Long drafts can be paged through.
5. Selecting `GMAIL` opens a prefilled Gmail compose window.
6. The user performs the final Send action.

Every reviewed message is also saved locally as:

```text
drafts/*.eml
```

---

## Auto-Send Flow

Auto-send is available only when explicitly enabled for a contact.

Example:

```json
{
  "name": "Example Contact",
  "email": "example@gmail.com",
  "auto_send": true
}
```

SMTP must also be configured.

When both conditions are satisfied:

```text
EMAIL
→ Contact
→ Topic
→ Immediate SMTP Send
```

There is **no review screen and no undo after delivery**.

Only enable:

```json
"auto_send": true
```

for contacts where this behavior is intentional.

---

# 5.6 YouTube

Select:

```text
YOUTUBE
```

The submenu contains:

```text
FAV SONGS
MOVIES
TYPE
```

---

## Favorite Songs

Select:

```text
FAV SONGS
```

to display saved music.

Favorites are stored in:

```text
favorites.json
```

Edit this file to customize the available songs.

---

## Movies

Select:

```text
MOVIES
```

to display saved movie shortcuts.

---

## Custom YouTube Request

Select:

```text
TYPE
```

The keyboard opens with a YouTube command prepared for editing.

Example:

```text
play YouTube Country Roads
```

---

# 5.7 Desktop Cursor

Select:

```text
CURSOR
```

to access desktop-control functions.

| Tile | Action |
|---|---|
| `MOVE X` | Move the cursor horizontally using left/right eye movement |
| `MOVE Y` | Left glance moves up; right glance moves down |
| `CLICK` | Left-click at the current cursor position |
| `R-CLICK` | Right-click |
| `SCROLL ↑` | Scroll upward |
| `SCROLL ↓` | Scroll downward |
| `PASTE` | Paste clipboard contents into the focused application |
| `FINE / FAST` | Toggle cursor speed |
| `RE-CENTER` | Reset the neutral iris position |
| `SAFE / UNSAFE` | Enable or disable desktop actions |
| `BACK` | Return to the home screen |

---

## Safe Mode

Safe mode prevents desktop actions from being executed accidentally.

When safe mode is active, actions such as:

- Clicking
- Scrolling
- Pasting
- Cursor movement

can be blocked.

Use the:

```text
SAFE / UNSAFE
```

tile to change the mode.

---

## Exit

Press:

```text
Esc
```

on the physical keyboard to close the application.

---

# 6. Optional: Gmail SMTP Auto-Send

You can skip this section if you only want the standard **review-before-send Gmail workflow**.

SMTP is needed for direct email delivery and contacts configured with:

```json
"auto_send": true
```

---

## 6.1 Create a Gmail App Password

Sign into your Google account and open:

https://myaccount.google.com/apppasswords

If App Passwords are unavailable, enable **2-Step Verification** first:

https://myaccount.google.com/security

Create a new App Password.

Example name:

```text
iris
```

Google will generate a 16-character password similar to:

```text
abcd efgh ijkl mnop
```

Remove the spaces:

```text
abcdefghijklmnop
```

Do **not** use your normal Gmail password.

---

# 6.2 Set SMTP Environment Variables

In the same Command Prompt used to run the application:

```bat
set "SMTP_HOST=smtp.gmail.com"
set "SMTP_PORT=587"
set "SMTP_USER=you@gmail.com"
set "SMTP_PASSWORD=abcdefghijklmnop"
set "EMAIL_FROM=you@gmail.com"
```

Then run:

```bat
run.bat
```

---

## Verify the Variables

```bat
echo %SMTP_HOST%
echo %SMTP_PORT%
echo %SMTP_USER%
echo %SMTP_PASSWORD%
echo %EMAIL_FROM%
```

---

## Make the Variables Permanent

The `set` command lasts only for the current terminal window.

To store the values permanently:

```bat
setx SMTP_HOST "smtp.gmail.com"
setx SMTP_PORT "587"
setx SMTP_USER "you@gmail.com"
setx SMTP_PASSWORD "abcdefghijklmnop"
setx EMAIL_FROM "you@gmail.com"
```

Close and reopen Command Prompt afterward.

---

# 6.3 Common SMTP Errors

| Error | Likely Fix |
|---|---|
| `535 Authentication failed` | Use a Gmail App Password rather than your normal password |
| `534 Application-specific password required` | Enable 2-Step Verification and create an App Password |
| Connection refused / timeout | The network may block port `587`; try another network or supported SMTP configuration |
| `SEND` tile never appears | Check whether all required SMTP environment variables are present |

---

# 7. Optional: Gemini Suggestions and Drafts

Gemini can improve several parts of Iris Assistant.

It can provide:

- Next-word predictions
- Intent suggestions
- Email drafts

Gemini is optional.

Without it, Iris Assistant falls back to bundled local logic.

---

## Gemini Features

### Next-Word Predictions

While typing, local predictions appear immediately.

Gemini suggestions may update the predictions asynchronously when configured.

### Intent Suggestions

Gemini can suggest possible actions on the assistant's ideas screen.

### Email Drafting

When selecting an email topic, Gemini attempts to create a natural-language draft.

If Gemini fails, Iris Assistant automatically uses a local email template.

---

## Enable Gemini

Set:

```bat
set "GEMINI_API_KEY=your-api-key-here"
set "GEMINI_MODEL=gemini-2.0-flash"
```

Then run:

```bat
run.bat
```

Create an API key at:

https://aistudio.google.com/apikey

---

## Store Gemini Settings Permanently

```bat
setx GEMINI_API_KEY "your-api-key-here"
setx GEMINI_MODEL "gemini-2.0-flash"
```

Then restart Command Prompt.

---

## Gemini Failure Behavior

If Gemini becomes unavailable because of:

- Invalid API key
- Network failure
- API quota
- Service error
- Authentication issue

the application continues working.

For example, email review may display:

```text
Draft: Local template
```

instead of:

```text
Draft: Gemini draft
```

---

## Optional OpenAI Fallback

If an OpenAI API key is configured:

```text
OPENAI_API_KEY
```

the application can attempt:

```text
Gemini
→ OpenAI
→ Local fallback
```

depending on the configured assistant logic.

---

# 8. Importing Contacts

Contacts can be imported from a CSV file.

You can export contacts from services such as:

- Google Contacts
- Microsoft Outlook

Activate the project environment:

```bat
.venv\Scripts\activate
```

Then run:

```bat
python import_contacts.py "%USERPROFILE%\Downloads\contacts.csv" --names "Sam,Priya"
```

The `--names` option imports only contacts whose names contain one of the specified fragments.

Example:

```text
Sam
Priya
```

To import all supported contacts, omit `--names`.

---

# 9. Testing Without a Camera

Many assistant features can be tested without webcam input.

Activate the environment:

```bat
.venv\Scripts\activate
```

---

## Preview Assistant Commands

```bat
python assistant_cli.py "play YouTube cat piano"
```

```bat
python assistant_cli.py "email Sam that I missed class"
```

```bat
python assistant_cli.py "search Google for flood maps" --execute
```

The `--execute` option allows browser actions.

For email actions, it can:

- Open Gmail compose
- Save an `.eml` draft

It does **not** automatically send via SMTP.

---

## Run Unit Tests

```bat
python -m unittest -v test_horizontal_logic test_assistant test_iris_tracking
```

The test suite is designed to run without requiring a webcam.

---

# 10. Configuration Reference

Application settings are stored in:

```text
config.json
```

Restart Iris Assistant after changing configuration values.

| Key | Meaning |
|---|---|
| `camera_index` | Webcam index. `0` is usually the built-in camera |
| `selection_mode` | `"auto"`, `"blink"`, or `"dwell"` |
| `nav_trigger` | Horizontal movement required before navigation begins |
| `nav_hold_s` | How long a side glance must be held before movement |
| `nav_repeat_s` | Repeat interval while holding a glance |
| `deadzone` | Amount of eye movement ignored as jitter |
| `speed_x` | Horizontal desktop cursor speed |
| `speed_y` | Vertical desktop cursor speed |
| `long_blink_min_s` | Minimum duration for selection blink |
| `long_blink_max_s` | Maximum duration for selection blink |
| `pause_blink_min_s` | Minimum duration for pause blink |
| `pause_blink_max_s` | Maximum duration for pause blink |
| `double_blink_*` | Double-blink gesture configuration |
| `triple_blink_run` | Enables triple-blink `RUN` |
| `email_topics` | Topics shown after selecting an email recipient |
| `quick_words` | Shortcut words on the keyboard's `QUICK` page |
| `gmail_account_index` | Which signed-in Google account Gmail compose should use |

---

# 11. Troubleshooting

| Problem | Possible Solution |
|---|---|
| App closes immediately with a traceback | Read the terminal error. A project file may be outdated or missing |
| `Camera unavailable` | Close Zoom, Teams, or other applications using the webcam |
| Wrong camera opens | Change `camera_index` in `config.json` |
| Marker jumps across several tiles | Recalibrate and improve lighting |
| Marker does not move | Move closer to the webcam and increase lighting |
| Marker moves but does not select | Adjust blink duration or use dwell mode |
| Double blink deletes words accidentally | Set `"double_blink_delete": false` |
| YouTube tile only types `youtube` | Make sure you are on the home screen rather than the keyboard |
| Gmail tile does not appear | Check whether the application expects `SEND` because SMTP is configured |
| Email SMTP authentication fails | Verify that you are using a Gmail App Password |
| Gemini drafts always look like templates | Check the terminal for Gemini API errors |
| Playwright Chromium installation fails | The project can continue using browser-search fallbacks |
| Eye control becomes inaccurate after moving | Use `CURSOR → RE-CENTER` or recalibrate |

---

# 12. What Problem This Solves

Many standard computer-input systems depend on:

- Hand movement
- Finger movement
- A mouse
- A keyboard
- A joystick
- A physical switch
- Head tracking
- Voice control

For users with severe motor impairments, some or all of these methods may be tiring, unreliable, or impossible.

Eye movement may remain a usable motor channel.

However, dedicated gaze-tracking systems frequently require specialized hardware.

Iris Assistant explores a different design approach.

---

## Webcam-Only Input

The project uses an ordinary webcam already present on many laptops.

No specialized eye-tracking device is required.

---

## Single-Axis Tracking

Instead of attempting full two-dimensional gaze estimation, the project primarily tracks:

```text
horizontal iris movement
```

This reduces complexity and can make calibration more repeatable with ordinary webcams.

---

## Large Interaction Targets

Rather than requiring the user to precisely position a mouse pointer over small buttons, Iris Assistant provides large tiles.

The marker moves between discrete interface options.

This makes the interaction better suited to relatively noisy webcam-based gaze estimation.

---

## Horizontal Signal Reused for Vertical Actions

Vertical gaze tracking can be less reliable with ordinary webcams.

For cursor mode, Iris Assistant can reuse horizontal eye gestures:

```text
Left glance  → Move up
Right glance → Move down
```

when vertical movement mode is active.

---

## Blink Selection

Many gaze interfaces rely primarily on dwell selection.

Long periods of staring at an interface element can become tiring.

Iris Assistant therefore uses deliberate blink selection when reliable eyelid tracking is available.

Dwell remains available as a fallback.

---

## Review Before Actions

Potentially important actions are designed around confirmation.

For example, the default email workflow is:

```text
Generate
→ Review
→ Open Gmail
→ User sends
```

Direct automatic sending requires explicit configuration for a specific contact.

---

## Local-First Design

Core functionality can operate locally.

Cloud integrations are optional.

Internet access is needed only for services such as:

- Gmail
- YouTube
- Google
- Gemini
- OpenAI

---

# 13. How It Differs From Existing Tools

| Existing Approach | Iris Assistant |
|---|---|
| Dedicated eye-tracking hardware such as Tobii or EyeTech | Uses a standard webcam |
| Full two-axis gaze estimation | Primarily tracks one horizontal iris axis |
| Free-floating gaze pointer | Uses large discrete interface tiles |
| Dwell-only selection | Blink selection with dwell fallback |
| Voice-first assistants | Designed to work silently |
| Interfaces that assume keyboard or mouse use | Main interface is gaze-driven |
| Cloud-first AI assistants | Core interaction can work locally |
| Automatic execution of communication actions | Email review is the default |
| Specialized eye-tracking sensors | Uses MediaPipe landmarks and ordinary camera input |

---

# 14. Known Limitations

## Webcam Accuracy

Webcam-only eye tracking is inherently less precise than specialized gaze-tracking hardware.

Iris Assistant is therefore designed around large tiles rather than pixel-perfect gaze control.

---

## Vertical Cursor Control

Vertical cursor movement reuses horizontal eye gestures.

Although controllable, this interaction may feel unintuitive at first.

---

## Fine Desktop Work

Tasks requiring very precise cursor placement may still be difficult.

Examples include:

- Detailed image editing
- Fine drawing
- Complex code editing
- Small UI controls

These are not the primary target use cases.

---

## Blink Detection

Blink detection depends on clear eyelid visibility.

Performance may decrease with:

- Poor lighting
- Strong reflections
- Thick glasses
- Webcam blur
- Extreme camera angles

Dwell selection is available as a fallback.

---

## Head Movement

Large changes in head position can affect calibration.

The user may need to:

```text
RE-CENTER
```

or recalibrate.

---

## SMTP Auto-Send

Once an email has been sent through SMTP, it cannot be undone by Iris Assistant.

Use:

```json
"auto_send": true
```

carefully.

---

## Gmail Account Selection

If multiple Google accounts are signed into the browser, the configured:

```text
gmail_account_index
```

must point to the intended account.

Always verify the active Gmail account before sending important messages.

---

## Third-Party AI Services

Gemini and OpenAI depend on external APIs.

Availability can be affected by:

- Network access
- API changes
- Authentication
- Usage quotas
- Service outages

The application uses local fallbacks when possible.

---

# 15. License and Attribution

This project is provided **as-is for educational and personal use**.

It uses or integrates with several third-party open-source projects and services.

### MediaPipe

Used for face and iris landmark detection.

**License:** Apache License 2.0

https://github.com/google-ai-edge/mediapipe

### OpenCV

Used for webcam capture and image processing.

**License:** Apache License 2.0

https://opencv.org/

### PyAutoGUI

Used for mouse, cursor, keyboard, and desktop automation.

**License:** BSD

https://github.com/asweigart/pyautogui

### Playwright

Used optionally for browser automation and YouTube result handling.

**License:** Apache License 2.0

https://playwright.dev/python/

### Tkinter

Used for the graphical interface.

Distributed with Python.

https://docs.python.org/3/library/tkinter.html

### Google Gemini

Optional cloud AI integration.

Use is subject to Google's API terms and policies.

### OpenAI

Optional fallback AI integration.

Use is subject to OpenAI's API terms and policies.

---

# Privacy and Safety Notes

Iris Assistant may handle sensitive personal information including:

- Contact names
- Email addresses
- Email content
- Calibration measurements

Do not publish local configuration files containing personal data.

Recommended `.gitignore` entries:

```gitignore
.venv/
contacts.json
calibration.json
drafts/
.env
__pycache__/
*.pyc
```

Never place API keys or Gmail App Passwords directly inside source files committed to GitHub.

Use environment variables instead.

---

# Quick Start

For users who already have Python 3.11 installed:

```bat
git clone <your-repository-url>
cd iris_assistant
run.bat
```

Follow the calibration instructions:

```text
CENTER
LEFT
RIGHT
CLOSE BOTH EYES
```

Then control Iris Assistant using:

```text
Look Left / Right → Navigate
Blink             → Select
Long Blink         → Pause
```

---

# Project Goal

Iris Assistant explores whether an ordinary laptop webcam can provide a practical alternative input channel for people who cannot reliably use conventional desktop controls.

Instead of attempting highly precise gaze tracking, it focuses on a simpler question:

> **Can reliable horizontal iris movement, large interface targets, blink selection, and carefully designed shortcuts provide meaningful hands-free access to everyday computer tasks?**
