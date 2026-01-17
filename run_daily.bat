@echo off
REM Lochross Outreach Bot - Daily Run
REM Run this via Windows Task Scheduler at 6 AM

cd /d "C:\Users\phili\Documents\projects\Autoemail"

REM Use WSL to run the Python script
wsl bash -c "cd /mnt/c/Users/phili/Documents/projects/Autoemail && source venv/bin/activate && python run_daily.py --max-jobs 10"

echo Done!
pause
