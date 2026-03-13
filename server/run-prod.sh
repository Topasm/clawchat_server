#!/bin/zsh
set -euo pipefail

cd /Users/ahrilab/Desktop/clawchat_server/server

export PATH="/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
export DEBUG="false"

exec /Users/ahrilab/Desktop/clawchat_server/server/venv/bin/uvicorn main:app --host 127.0.0.1 --port 8000
