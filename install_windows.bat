@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>nul
if errorlevel 1 (
  echo Python Launcher ne naiden. Ustanovite Python 3.11+ s python.org i vklyuchite Add Python to PATH.
  pause
  exit /b 1
)
echo Sozdanie novogo chistogo okruzheniya .venv_bi...
py -3 -m venv --clear .venv_bi
if errorlevel 1 goto :error
".venv_bi\Scripts\python.exe" -m pip install --upgrade pip setuptools wheel
if errorlevel 1 goto :error
".venv_bi\Scripts\python.exe" -m pip install --upgrade --force-reinstall typing-extensions==4.16.0
if errorlevel 1 goto :error
".venv_bi\Scripts\python.exe" -m pip install --upgrade -r requirements.txt
if errorlevel 1 goto :error
".venv_bi\Scripts\python.exe" -c "import typing_extensions, vl_convert; from company_analyst.altair_compat import load_altair; from PySide6.QtWebEngineWidgets import QWebEngineView; print('Altair', load_altair().__version__, '- OK')"
if errorlevel 1 goto :error
echo.
echo Ustanovka i proverka zaversheny. Zapustite run_windows.bat
pause
exit /b 0
:error
echo.
echo Oshibka ustanovki ili proverki. Proverte internet i versiyu Python.
pause
exit /b 1
