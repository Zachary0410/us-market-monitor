@echo off
rem ===========================================================
rem  Double-click this file to open the web page.
rem
rem  It starts a local Streamlit server and opens your browser.
rem  Keep this window open while you use the page:
rem  press Ctrl+C here (or just close this window) to stop it.
rem
rem  The scheduled task does NOT start this server. The task only
rem  writes data files; the web page is started by this file.
rem
rem  NOTE 1: keep this file ASCII-only. cmd.exe reads .bat files
rem  using the system codepage, and non-ASCII comments can break
rem  the commands. The Chinese docs live in README.md.
rem
rem  NOTE 2: avoid "if ... ( ... )" blocks. cmd.exe mis-parses
rem  parenthesised blocks when the file has LF-only line endings,
rem  so this script uses "goto :label" instead.
rem
rem  NOTE 3: the python.exe path below is hard-coded on purpose.
rem  Update it if you ever install a different Python version.
rem
rem  NOTE 4: Streamlit asks for an email address on its very first run
rem  and WAITS for an answer before starting the server. If you ever see
rem  "Email:" in this window, just press Enter. You can also get rid of
rem  the prompt for good with a file at:
rem      %USERPROFILE%\.streamlit\credentials.toml
rem ===========================================================

title US Market Monitor - Web

cd /d "%~dp0"

set PYTHON_EXE=C:\Users\60411\AppData\Local\Programs\Python\Python313\python.exe

if not exist "%PYTHON_EXE%" goto :no_python

rem Do not start a second server if one is already listening on 8501
netstat -ano | findstr ":8501" | findstr "LISTENING" >nul
if not errorlevel 1 goto :already_running

echo Starting the web page ...
echo Keep this window open while you use the page.
echo Press Ctrl+C here to stop it.
echo.
echo If your browser does not open by itself, visit:
echo     http://localhost:8501
echo.

rem Turn off usage-statistics reporting; extra arguments are forwarded to streamlit
"%PYTHON_EXE%" -m streamlit run app.py --browser.gatherUsageStats=false %*

echo.
echo The web server has stopped.
pause
exit /b 0

:already_running
echo The web page is ALREADY running.
echo Open this address in your browser:
echo     http://localhost:8501
echo.
echo To restart it, stop the old server first.
echo You can find its PID with:  netstat -ano ^| findstr :8501
echo Then stop it with:          taskkill /F /PID ^<that PID^>
echo.
pause
exit /b 0

:no_python
echo [ERROR] Python not found:
echo         %PYTHON_EXE%
echo         Open this .bat file and fix the PYTHON_EXE path.
echo.
pause
exit /b 1
