@echo off
REM ==========================================================================
REM  PriceLens BH - one-click start (Windows)
REM  Double-click this file. First run: about 2-3 minutes (installs packages).
REM  Later runs: a few seconds. Close this window to stop the app.
REM ==========================================================================
setlocal
cd /d "%~dp0"
title PriceLens BH
set "APP=src\dashboard\page.py"

echo.
echo  === PriceLens BH ===
echo.

REM --- 1. Find Python -------------------------------------------------------
set "PY="
py --version >nul 2>nul && set "PY=py"
if not defined PY python --version >nul 2>nul && set "PY=python"
if not defined PY (
    echo  Python is not installed on this computer.
    echo  Install it from https://www.python.org/downloads/
    echo  and tick "Add python.exe to PATH", then double-click this file again.
    goto :fail
)

REM --- 2. Create the project environment (first run only) -------------------
if not exist ".venv\Scripts\python.exe" (
    echo  [1/4] Creating the Python environment - first run only...
    %PY% -m venv .venv || goto :fail
) else (
    echo  [1/4] Python environment found.
)
set "VPY=.venv\Scripts\python.exe"

REM --- 3. Install the packages listed in requirements.txt -------------------
echo  [2/4] Checking packages - the first run takes a few minutes...
"%VPY%" -m pip install --disable-pip-version-check -q -r requirements.txt || goto :fail

REM --- 4. Dataset 3 check and data preparation ------------------------------
echo  [3/4] Checking the data files...
"%VPY%" -m scripts.download_sources
echo        The app also runs without Dataset 3; only the weights are then missing.
if not exist "data\processed" mkdir "data\processed"
"%VPY%" -m src.pipeline.run > "data\processed\pipeline_log.txt" 2>&1
if errorlevel 1 (
    type "data\processed\pipeline_log.txt"
    goto :fail
)
echo        Data prepared - details in data\processed\quality_report.md

REM --- 5. Skip Streamlit's first-run email question --------------------------
if not exist "%USERPROFILE%\.streamlit\credentials.toml" (
    if not exist "%USERPROFILE%\.streamlit" mkdir "%USERPROFILE%\.streamlit"
    > "%USERPROFILE%\.streamlit\credentials.toml" echo [general]
    >> "%USERPROFILE%\.streamlit\credentials.toml" echo email = ""
)

REM --- 6. Start the app -----------------------------------------------------
echo  [4/4] Opening PriceLens BH in your browser. Close this window to stop it.
echo.
"%VPY%" -m streamlit run "%APP%"
goto :eof

:fail
echo.
echo  Something went wrong. Take a screenshot of this window and send it to the group.
pause
exit /b 1
