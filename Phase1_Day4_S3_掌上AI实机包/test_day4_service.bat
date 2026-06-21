@echo off
cd /d "%~dp0"
set ENV_PATH=..\local_siliconflow.env
set MOCK_LLM=1
python run_day4_selftest.py
pause
