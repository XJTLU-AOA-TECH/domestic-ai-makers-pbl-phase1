@echo off
cd /d "%~dp0"
set ENV_PATH=..\local_siliconflow.env
set PORT=8000
set MOCK_LLM=0
python -c "import socket; s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM); s.connect(('8.8.8.8',80)); ip=s.getsockname()[0]; s.close(); print(f'=== Day4 Device-to-Agent Bridge ==='); print(f'Local: http://127.0.0.1:%PORT%/dashboard'); print(f'Device Base URL: http://{ip}:%PORT%/v1'); print(f'Model: pocket-campus-agent'); print(f'API Key: classroom-demo-key'); print()"
python -m uvicorn cloud_service:app --host 0.0.0.0 --port 8000
pause
