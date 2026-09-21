@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv_bi\Scripts\python.exe" (
  echo Pervyi zapusk: sozdayu chistoe okruzhenie i ustanavlivayu biblioteki...
  where py >nul 2>nul
  if errorlevel 1 (
    echo Python Launcher ne naiden. Ustanovite Python 3.11 ili 3.12 s python.org.
    pause
    exit /b 1
  )
  py -3 -m venv .venv_bi
  if errorlevel 1 goto :error
  ".venv_bi\Scripts\python.exe" -m pip install --upgrade pip setuptools wheel
  if errorlevel 1 goto :error
  ".venv_bi\Scripts\python.exe" -m pip install --upgrade -r requirements.txt
  if errorlevel 1 goto :error
)

".venv_bi\Scripts\python.exe" -c "import typing_extensions, vl_convert; from company_analyst.altair_compat import load_altair; from PySide6.QtWebEngineWidgets import QWebEngineView; load_altair()" >nul 2>nul
if errorlevel 1 (
  echo Vosstanavlivayu proverennye versii grafikov...
  ".venv_bi\Scripts\python.exe" -m pip install --upgrade --force-reinstall typing-extensions==4.16.0 altair==5.5.0 vl-convert-python==1.9.0
  if errorlevel 1 goto :repair_error
  ".venv_bi\Scripts\python.exe" -m pip install --upgrade -r requirements.txt
  if errorlevel 1 goto :repair_error
)

".venv_bi\Scripts\python.exe" main.py
if errorlevel 1 pause
exit /b 0

:repair_error
echo Ne udalos vosstanovit biblioteki. Zapustite repair_windows.bat.
pause
exit /b 1

:error
echo Oshibka pervichnoi ustanovki. Proverte internet i zapustite install_windows.bat.
pause
exit /b 1
