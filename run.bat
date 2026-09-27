@echo off
REM Launcher: starts the face cursor and opens the keyboard.
cd /d "%~dp0"
if not exist .venv (
  echo Creating virtual environment with Python 3.11...
  py -3.11 -m venv .venv
  call .venv\Scripts\activate
  pip install -r requirements.txt
) else (
  call .venv\Scripts\activate
)
start "" "%~dp0keyboard\index.html"
python face_cursor.py
pause
