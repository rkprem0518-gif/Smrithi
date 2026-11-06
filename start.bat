@echo off
REM Double-click to set up and run Smriti (family, elder and care-team apps).
cd /d "%~dp0"
where py >nul 2>nul
if %errorlevel%==0 (py -3 start.py %*) else (python start.py %*)
pause
