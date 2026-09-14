@echo off
rem ===========================================================
rem  Called by Windows Task Scheduler. You can also double-click
rem  this file to run one report manually.
rem
rem  It does three things:
rem    1. cd to the project folder
rem    2. run run_daily.py
rem    3. append everything to logs\scheduled.log
rem
rem  NOTE: the python.exe path below is hard-coded on purpose,
rem  because a scheduled task's PATH is not reliable. Update it
rem  if you ever install a different Python version.
rem
rem  NOTE: keep this file ASCII-only. cmd.exe reads .bat files
rem  using the system codepage, and non-ASCII comments can break
rem  the commands. The Chinese docs live in README.md.
rem ===========================================================

cd /d "%~dp0"

if not exist "logs" mkdir "logs"

echo. >> "logs\scheduled.log"
echo ===== %date% %time% ===== >> "logs\scheduled.log"

rem Write UTF-8 so the log is readable in VS Code
set PYTHONIOENCODING=utf-8

"C:\Users\60411\AppData\Local\Programs\Python\Python313\python.exe" run_daily.py >> "logs\scheduled.log" 2>&1

rem Pass the exit code through so Task Scheduler can tell success from failure
exit /b %ERRORLEVEL%
