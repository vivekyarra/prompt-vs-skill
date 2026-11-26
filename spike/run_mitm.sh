#!/usr/bin/env bash
# Design B: HTTPS interception via mitmproxy for apps using the DEFAULT Flagsmith hosts.
# Usage: spike/run_mitm.sh <venv-dir>
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
VENV="${1:?venv dir with mitmproxy+flagsmith+playwright}"
LOG="$HERE/capture_mitm.jsonl"
CA="$HOME/.mitmproxy/mitmproxy-ca-cert.pem"
rm -f "$LOG"
"$VENV/bin/mitmdump" -q -p 8080 -s "$HERE/mitm_addon.py" --set spike_log="$LOG" >"$HERE/mitm.log" 2>&1 & MITM=$!
sleep 4
P=http://127.0.0.1:8080
unset SPIKE_API_URL SPIKE_EVENTS_URL
count() { echo "   -> $(grep -c "\"$1\"" "$LOG" 2>/dev/null || echo 0) total captured so far"; }

echo "== node SDK, NODE_USE_ENV_PROXY=1 + HTTPS_PROXY + NODE_EXTRA_CA_CERTS"
(cd "$HERE/node" && NODE_USE_ENV_PROXY=1 HTTPS_PROXY=$P https_proxy=$P NODE_EXTRA_CA_CERTS=$CA node run.mjs 2>&1 | tail -2); count via
echo "== node SDK, HTTPS_PROXY only (NO NODE_USE_ENV_PROXY) -- expect NOT captured"
N0=$(grep -c via "$LOG" 2>/dev/null || echo 0)
(cd "$HERE/node" && HTTPS_PROXY=$P https_proxy=$P NODE_EXTRA_CA_CERTS=$CA timeout 25 node run.mjs 2>&1 | tail -2); echo "   -> new captures: $(( $(grep -c via "$LOG") - N0 ))"
echo "== python SDK, HTTPS_PROXY + REQUESTS_CA_BUNDLE + SSL_CERT_FILE"
HTTPS_PROXY=$P https_proxy=$P REQUESTS_CA_BUNDLE=$CA SSL_CERT_FILE=$CA "$VENV/bin/python" "$HERE/python/run.py" 2>&1 | tail -2; count via
echo "== js SDK (isomorphic, under node), NODE_USE_ENV_PROXY=1"
(cd "$HERE/js" && NODE_USE_ENV_PROXY=1 HTTPS_PROXY=$P https_proxy=$P NODE_EXTRA_CA_CERTS=$CA node run_node.mjs 2>&1 | tail -2); count via
echo "== chromium via playwright (proxy + ignore_https_errors), UMD browser bundle"
HTTPS_PROXY= "$VENV/bin/python" "$HERE/js/browser_spike.py" --proxy $P 2>&1 | tail -3; count via
kill $MITM
echo "total captured: $(wc -l < "$LOG")"
