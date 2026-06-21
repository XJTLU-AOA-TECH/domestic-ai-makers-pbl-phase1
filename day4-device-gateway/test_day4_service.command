#!/bin/zsh
set -euo pipefail
cd "$(dirname "$0")"
PYTHON_BIN="/Users/zcmbp/.pyenv/versions/3.10.17/bin/python3"
if [ ! -x "$PYTHON_BIN" ]; then
  PYTHON_BIN="$(command -v python3)"
fi
export ENV_PATH="../local_siliconflow.env"
export MOCK_LLM=1
"$PYTHON_BIN" run_day4_selftest.py
