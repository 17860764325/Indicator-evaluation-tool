@echo off
cd /d "%~dp0"
python -c "import PIL" >nul 2>&1
if errorlevel 1 (
  echo Installing Pillow...
  python -m pip install -r requirements.txt
  if errorlevel 1 exit /b 1
)
python app.py --open
pause
