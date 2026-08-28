#!/usr/bin/env bash
# Restart the Atlas dashboard on 0.0.0.0:8501 (idempotent).
PORT=8501
PIDS=$(ss -tlnp 2>/dev/null | awk -v p=":$PORT" '$4 ~ p {print $NF}' | grep -oP 'pid=\K[0-9]+' | sort -u)
for p in $PIDS; do kill "$p" 2>/dev/null; done
sleep 2
cd "$(dirname "$0")/.."
setsid bash -c 'exec streamlit run dashboard/app.py --server.address 0.0.0.0 --server.port 8501 --server.headless true > /tmp/opencode/dashboard.log 2>&1' < /dev/null &
sleep 10
curl -s -m 5 -o /dev/null -w "dashboard HTTP %{http_code}\n" "http://127.0.0.1:$PORT"
