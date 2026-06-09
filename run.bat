@echo off
set PLAYWRIGHT_BROWSERS_PATH=C:\A\playwright
cd /d C:\A\mgkh-local-agent
call venv\Scripts\activate
python main.py >> logs\agent.log 2>&1
