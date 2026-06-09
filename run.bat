@echo off
cd /d C:\A\mgkh-local-agent
call venv\Scripts\activate
python main.py >> logs\agent.log 2>&1
