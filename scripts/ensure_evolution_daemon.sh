#!/usr/bin/env bash
# Ensure exactly ONE evolution daemon is running (idempotent).
cd "$(dirname "$0")/.."
PIDS=$(pgrep -f "evolution_daemon.py")
COUNT=$(echo "$PIDS" | grep -c .)
if [ "$COUNT" -gt 1 ]; then
  echo "found $COUNT daemons, stopping all to restart one..."
  for p in $PIDS; do kill "$p" 2>/dev/null; done
  sleep 2
  COUNT=0
fi
if [ "$COUNT" -eq 0 ]; then
  mkdir -p data
  setsid bash -c 'exec python3 scripts/evolution_daemon.py --interval-hours 6 >> data/evolution_daemon.log 2>&1' < /dev/null &
  sleep 3
fi
echo "evolution daemons now running: $(pgrep -f evolution_daemon.py | wc -l) (pid: $(pgrep -f evolution_daemon.py | head -1))"
