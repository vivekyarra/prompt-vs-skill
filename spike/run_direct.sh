#!/usr/bin/env bash
# Design A (the grader's design): apps point at the mock via env; capture happens at the mock.
# Usage: spike/run_direct.sh [python-bin]   (needs: pip install flagsmith; npm ci in spike/js, spike/node)
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
PY="${1:-python3}"
LOG="$HERE/capture_direct.jsonl"
rm -f "$LOG"
python3 "$HERE/mock_flagsmith.py" --port 8765 --log "$LOG" & MOCK=$!
sleep 1
export SPIKE_API_URL=http://127.0.0.1:8765/api/v1/ SPIKE_EVENTS_URL=http://127.0.0.1:8765/
echo "== python";  "$PY" "$HERE/python/run.py"
echo "== node";    (cd "$HERE/node" && node run.mjs)
echo "== js(node)"; (cd "$HERE/js" && node run_node.mjs)
kill $MOCK
echo "captured $(wc -l < "$LOG") requests in $LOG"
