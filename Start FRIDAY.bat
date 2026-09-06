@echo off
REM ===================================================================
REM  Double-clickable launcher for F.R.I.D.A.Y.
REM
REM  Double-clicking main.py directly does NOT work: Windows hands .py
REM  files to C:\WINDOWS\py.exe, which runs the system Python 3.13 --
REM  and that interpreter has no google-genai and no groq, so the run
REM  dies at brain.py before the mic ever opens, and the console window
REM  closes too fast to read the error.
REM
REM  This script uses the project venv instead, forces UTF-8 so Telugu
REM  and Devanagari replies cannot raise UnicodeEncodeError, and holds
REM  the window open at the end so any error stays on screen.
REM ===================================================================

cd /d "%~dp0"
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
title F.R.I.D.A.Y.

if not exist ".venv\Scripts\python.exe" (
    echo.
    echo   Could not find .venv\Scripts\python.exe
    echo   Expected it in: %CD%
    echo.
    echo   The virtual environment is missing or this file was moved out
    echo   of the project folder.
    echo.
    pause
    exit /b 1
)

".venv\Scripts\python.exe" main.py

echo.
echo ------------------------------------------------------------
echo  F.R.I.D.A.Y. has stopped. Press any key to close this window.
echo ------------------------------------------------------------
pause >nul
