@echo off
title PolyGuard
cd /d "%~dp0"
echo.
echo  ==============================================
echo    PolyGuard - starting up
echo    Keep this window open while you use it.
echo  ==============================================
echo.
set "PY="
rem 1) Look for 64-bit Python in the usual install folders (skips 32-bit ones)
for /d %%d in ("%LOCALAPPDATA%\Programs\Python\Python3*") do (
  echo %%~nxd| findstr /c:"-32" >nul || if exist "%%d\python.exe" set PY="%%d\python.exe"
)
if not defined PY for /d %%d in ("%LOCALAPPDATA%\Python\pythoncore-3*") do (
  echo %%~nxd| findstr /c:"-32" >nul || if exist "%%d\python.exe" set PY="%%d\python.exe"
)
if not defined PY for /d %%d in ("%ProgramFiles%\Python3*") do (
  if exist "%%d\python.exe" set PY="%%d\python.exe"
)
rem 2) Otherwise fall back to the py launcher or PATH
if not defined PY ( py -3-64 --version >nul 2>&1 && set "PY=py -3-64" )
if not defined PY ( python --version >nul 2>&1 && set "PY=python" )
if not defined PY (
  echo.
  echo  Python was not found. Install Python 3.13 "Windows installer (64-bit)"
  echo  from python.org, tick "Add python.exe to PATH", restart the laptop,
  echo  then double-click this file again.
  pause
  exit /b
)
%PY% check_python.py
if errorlevel 1 (
  pause
  exit /b
)
echo  Step 1 of 2: checking the add-ons PolyGuard needs...
echo  (the first time this takes 2-5 minutes)
%PY% -m pip install --disable-pip-version-check --only-binary=:all: -q -r requirements.txt
if errorlevel 1 (
  echo.
  echo  Something went wrong installing add-ons. Check your internet and try again.
  pause
  exit /b
)
echo  Step 2 of 2: opening PolyGuard in your browser...
start "" cmd /c "timeout /t 8 >nul & start http://localhost:8501"
%PY% -m streamlit run app.py
pause
