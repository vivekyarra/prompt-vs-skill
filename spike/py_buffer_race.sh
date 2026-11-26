#!/usr/bin/env bash
# Shows whether the python SDK's exposure survives with max_buffer_items=1 (official prompt advice) vs default+flush.
HERE="$(cd "$(dirname "$0")" && pwd)"
PY="${1:-python3}"
LOG="$HERE/capture_pybuf.jsonl"
python3 "$HERE/mock_flagsmith.py" --port 8766 --log "$LOG" & MOCK=$!
sleep 1
export SPIKE_API_URL=http://127.0.0.1:8766/api/v1/ SPIKE_EVENTS_URL=http://127.0.0.1:8766/
for mode in 1 default; do
  for i in 1 2 3 4 5 6; do
    rm -f "$LOG"
    if [ $mode = 1 ]; then SPIKE_PY_MAXBUF=1 "$PY" "$HERE/python/run.py" >/dev/null 2>&1; else "$PY" "$HERE/python/run.py" >/dev/null 2>&1; fi
    echo "maxbuf=$mode run=$i exposures=$(grep -c flag_exposure "$LOG") spike_events=$(grep -c '"event": "spike_event"' "$LOG")"
  done
done
kill $MOCK
