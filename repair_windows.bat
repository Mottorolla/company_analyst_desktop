@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv_bi\Scripts\python.exe" (
  echo Chistoe okruzhenie ne naideno. Zapuskayu install_windows.bat...
  call install_windows.bat
  exit /b %errorlevel%
)

echo Vosstanovlenie bibliotek Altair...
".venv_bi\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 goto :error
".venv_bi\Scripts\python.exe" -m pip install --upgrade --force-reinstall typing-extensions==4.16.0 altair==5.5.0 vl-convert-python==1.9.0
if errorlevel 1 goto :error
".venv_bi\Scripts\python.exe" -m pip install --upgrade -r requirements.txt
if errorlevel 1 goto :error
".venv_bi\Scripts\python.exe" -c "import typing_extensions, vl_convert; from company_analyst.altair_compat import load_altair; print('Altair', load_altair().__version__, '- OK')"
if errorlevel 1 goto :error

echo.
echo Vosstanovlenie zaversheno. Zapustite run_windows.bat.
pause
exit /b 0

:error
echo.
echo Ne udalos vosstanovit biblioteki. Proverte internet, zatem povtorite zapusk.
pause
exit /b 1
