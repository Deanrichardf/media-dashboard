@echo off
:: Sets up a weekly Windows Task Scheduler job to run updater.py every Monday at 08:00.
:: Run this file once as Administrator (right-click → Run as administrator).

set REPO=%~dp0
set PYTHON=python
set TASK_NAME=BooksAndPodcastsUpdater

:: Install Python dependencies
echo Installing Python dependencies...
%PYTHON% -m pip install -r "%REPO%requirements.txt" --quiet

:: Create the scheduled task
schtasks /Create /TN "%TASK_NAME%" /TR "\"%PYTHON%\" \"%REPO%updater.py\"" ^
  /SC WEEKLY /D MON /ST 08:00 /RL HIGHEST /F

if %ERRORLEVEL% EQU 0 (
  echo.
  echo Task "%TASK_NAME%" created successfully.
  echo It will run every Monday at 08:00 while your PC is on.
  echo To run it immediately: schtasks /Run /TN "%TASK_NAME%"
) else (
  echo Failed to create task. Make sure you ran this as Administrator.
)
pause
