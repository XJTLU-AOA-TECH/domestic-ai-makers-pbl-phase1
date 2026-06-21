#!/bin/zsh
set -euo pipefail
cd "$(dirname "$0")"

PYTHON_BIN="/Users/zcmbp/.pyenv/versions/3.10.17/bin/python3"
if [ ! -x "$PYTHON_BIN" ]; then
  PYTHON_BIN="$(command -v python3)"
fi

export ENV_PATH="../local_siliconflow.env"
export PORT="${PORT:-8000}"
export MOCK_LLM="${MOCK_LLM:-0}"

LAN_IP="$(python3 -c "import socket; s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM); s.connect(('8.8.8.8',80)); print(s.getsockname()[0]); s.close()" 2>/dev/null || echo 127.0.0.1)"
echo "=== Day4 Device-to-Agent Bridge ==="
echo "Local: http://127.0.0.1:${PORT}/dashboard"
echo "Device Base URL: http://${LAN_IP}:${PORT}/v1"
echo "Model: pocket-campus-agent"
echo "API Key: classroom-demo-key"
echo

"$PYTHON_BIN" -m uvicorn cloud_service:app --host 0.0.0.0 --port "$PORT"
