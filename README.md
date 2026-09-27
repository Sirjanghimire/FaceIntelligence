# eye_control — face-driven cursor + keyboard

Move the mouse with your head (or eyes), click by opening your mouth, type on a
big on-screen keyboard with word prediction and speech. Everything runs locally
on a laptop webcam. This is the foundation the AI-assistant layer will sit on.

```
eye_control/
├── README.md            ← you are here
├── requirements.txt     ← pip install -r requirements.txt
├── config.json          ← every threshold/gain, no code edits needed
├── run.bat              ← double-click launcher (Windows)
├── tracking.py          ← FaceTracker: landmarks → yaw/pitch/gaze/mouth/blink  (shared)
├── test_camera.py       ← step 1: webcam works?
├── face_test.py         ← step 2: MediaPipe sees face? shows live numbers for tuning
├── face_cursor.py       ← step 3: THE controller (head/gaze cursor + mouth click)
├── calibration.py       ← step 4 (optional): 9-point gaze calibration → calibration.json
└── keyboard/
    └── index.html       ← step 5: adaptive keyboard (open in Chrome/Edge)
```

## Setup (once)

```bat
cd eye_control
py -3.11 -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

mediapipe is pinned to 0.10.14 because it is the last line that ships the
`mp.solutions.face_mesh` API on Python 3.11 with no extra downloads.

## Run, in this order

| Step | Command | What "working" looks like |
|---|---|---|
| 1 | `python test_camera.py` | You see yourself, mirrored. Press **Q**. |
| 2 | `python face_test.py` | Coloured dots on your irises (blue), eye corners (green), mouth (orange), nose (pink). Numbers update. |
| 3 | `python face_cursor.py` | Face the screen and hold still for a second → "Centred". Turn head slightly → cursor drifts that way; face the screen → it stops. Open mouth → click. |
| 4 | `start keyboard\index.html` (it is a web page, NOT a Python script — never `python index.html`), press **F11** for fullscreen | Type by pointing and opening your mouth. |
| 5 | `python calibration.py` (optional) | Look at 9 dots. Then press **G** in face_cursor to try gaze mode. |

### Tune it in step 2 before you rely on it
In `face_test.py`, open your mouth wide and read **MAR**, then close your
eyes and read **EAR**. Set in `config.json`:

* `mouth_open_threshold` ≈ 60 % of your wide-open MAR (typical 0.30–0.40)
* `blink_threshold` ≈ halfway between eyes-open and eyes-closed EAR (typical 0.17–0.21)

### Live keys inside the face_cursor window
`q` quit · `c` re-centre · `p` pause · `g` joystick → head → gaze · `m` mouth · `b` blink · `d` dwell · `[` `]` slower / faster

## Why it's built this way (speed + low fatigue)

* **Joystick mode by default.** Your head is a joystick: a small turn makes
  the cursor drift slowly, a bigger turn speeds it up, facing the screen stops
  it. You never have to hold your head at an exact angle, which is what makes
  position-mapping tiring and shaky. Switch to `head` mode later for speed.
* **Head *rotation*, not head *position*.** The cursor reads the nose relative
  to the cheeks/forehead/chin, so turning your head a few degrees is enough and
  leaning or sliding in the chair doesn't move the cursor.
* **Five-landmark averaging + two One-Euro filter stages + jitter lock.** The
  nose/cheek/chin points are averaged, the head angles are filtered, the screen
  position is filtered again, and wobble under 3 px is thrown away. Lower
  `smoothing_min_cutoff` (0.4) if still shaky; raise (1.0) if laggy.
* **Deadzone** so a resting head keeps the cursor parked.
* **Cursor freezes the moment your mouth opens**, so the click lands where you
  were pointing, not where your head drifted while opening.
* **Short open = left click, hold 1 s = right click**; false clicks are rare
  because a 0.12 s minimum hold filters talking/twitches.
* **Huge tiles, no dead gaps, undo key, delete-word key, 4 predictions,
  quick phrases, auto-speak on `.` `?` `!`.** Fewer selections per sentence is
  the single biggest fatigue win.
* **Groups layout** (A–I / J–R / S–Z → smaller) for days when precision is poor;
  **QWERTY/ABC** for speed once pointing is good.
* Gaze mode is optional because webcam-only gaze is ±3–5 cm at best; head mode
  is what people actually type with. Gaze becomes useful later as a *coarse
  jump* combined with head fine-tuning (the calibration already fits both).

## Roadmap — files to add next (in this order)

| # | File | Job | Notes |
|---|---|---|---|
| 1 | `gestures.py` | Pull ClickEngine out of face_cursor.py; add **eyebrow raise** (toggle scroll mode), **head nod/shake**, **look-away pause** | `tracking.py` already outputs `brow` |
| 2 | `scroll_mode.py` | In scroll mode: head up/down → `pyautogui.scroll()` with acceleration; needed for Instagram Reels / YouTube feeds | Mouth open exits scroll mode |
| 3 | `keyboard/bridge.py` | Tiny local WebSocket (`websockets`) so the browser keyboard can **type into any app** via `pyautogui.write()` and send text to the LLM | Keyboard already has a Copy button as the stop-gap |
| 4 | `assistant/llm.py` | Gemini/OpenAI/Claude API wrapper: sentence completion from 2–3 words, reply suggestions, intent → command JSON | Send the whole typed context each call |
| 5 | `assistant/intents.py` | Map LLM JSON → actions: `open_url("youtube.com")`, `search("...")`, `scroll`, `play/pause`, `volume` | Whitelist actions; never let the LLM run arbitrary shell |
| 6 | `browser_control.py` | Playwright (Chromium) so YouTube/Instagram are driven **by API**, not by pixel-hunting with the cursor — far faster and less tiring | Keep pyautogui as fallback for arbitrary apps |
| 7 | `keyboard/` → add `commands.html` | Big command tiles: "Open YouTube", "Search…", "Next reel", "Read this page aloud" | Same tile system as index.html |
| 8 | `voice_out.py` | pyttsx3 / edge-tts for offline, higher-quality speech than the browser's | |
| 9 | `profiles/` | Per-user `config.json` + `calibration.json` + learned vocabulary | Lets the teammate test without wrecking your tuning |
| 10 | `launcher.py` | One tray/console app that starts tracking, the bridge and the browser | Replaces run.bat |

## Troubleshooting

* **Nothing installs / mediapipe error** → make sure `python --version` says 3.11.x inside the venv.
* **Black camera window** → change `"camera_index"` to 1 in config.json.
* **Cursor creeps while I face the screen** → press `c` (re-centre) while facing it; raise `joystick_deadzone` to 0.02.
* **Cursor too slow / too fast** → press `[` or `]`, or change `joystick_speed_*`.
* **Cursor still shaky** → lower `smoothing_min_cutoff` to 0.4 and `signal_min_cutoff` to 0.5. Better, even lighting on your face matters more than any setting.
* **`SyntaxError` on index.html** → you ran it with Python. It's a web page: `start keyboard\index.html`.
* **Clicks when I talk** → raise `mouth_open_threshold` or `mouth_min_hold_s` to 0.2.
* **macOS** → grant Terminal/VS Code Accessibility + Camera permission or pyautogui can't move the mouse.
* **Cursor flies to a corner and everything stops** → FAILSAFE is already off; if you re-enable it, expect that.
