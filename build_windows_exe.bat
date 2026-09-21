@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv_bi\Scripts\python.exe" (
  echo Snachala zapustite install_windows.bat
  pause
  exit /b 1
)
call .venv_bi\Scripts\activate.bat
pip install -r requirements-build.txt
pyinstaller --noconfirm --clean --windowed --name CompanyAnalyst --collect-all altair --collect-all vl_convert --collect-all PySide6 main.py
if errorlevel 1 (
  echo Oshibka sborki.
  pause
  exit /b 1
)
echo.
echo Gotovo: dist\CompanyAnalyst\CompanyAnalyst.exe
pause
