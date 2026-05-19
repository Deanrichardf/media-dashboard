@echo off
:: Registers a weekly Windows Task Scheduler job to run updater.py every Monday at 08:00.
:: No Administrator rights needed.

set REPO=%~dp0
set PYTHON=python
set TASK_NAME=BooksAndPodcastsUpdater

echo Installing Python dependencies...
%PYTHON% -m pip install -r "%REPO%requirements.txt" --quiet

echo Creating scheduled task...
schtasks /Create /TN "%TASK_NAME%" /TR "\"%PYTHON%\" \"%REPO%updater.py\"" /SC WEEKLY /D MON /ST 08:00 /F

if %ERRORLEVEL% EQU 0 (
  echo.
  echo Task "%TASK_NAME%" created. Runs every Monday at 08:00.
  echo To trigger it now: schtasks /Run /TN "%TASK_NAME%"
) else (
  echo Failed to create task.
)
pause
