@echo off
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
  py -3.11 -m venv .venv
  if errorlevel 1 goto :failed
)
call .venv\Scripts\activate
if not exist .venv\.core_ready (
  python -m pip install -r requirements.txt
  if errorlevel 1 goto :failed
  python -m playwright install chromium
  if errorlevel 1 echo Chromium could not install. YouTube playback will open search results instead.
  type nul > .venv\.core_ready
)
if /I "%IRIS_INTENT_ENGINE%"=="laya" (
  if not exist .venv\.laya_ready (
    python -m pip install -r requirements-laya.txt
    if errorlevel 1 goto :failed
    type nul > .venv\.laya_ready
  )
)
python -c "import json,pathlib; p=pathlib.Path('calibration.json'); assert p.exists() and json.loads(p.read_text()).get('model')=='horizontal-iris-v1'" >nul 2>&1
if errorlevel 1 (
  echo Follow the CENTER, LEFT and RIGHT dots with only your eyes.
  python calibrate.py
  if errorlevel 1 goto :failed
)
python iris_control.py
if errorlevel 1 goto :failed
exit /b 0
:failed
echo Please check the error above and README.md.
pause
exit /b 1
