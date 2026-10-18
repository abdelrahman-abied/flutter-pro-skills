#!/usr/bin/env bash
# Print one status line per benchmark run (read-only): done/running, elapsed, idle time, tool calls,
# files the agent changed. A run with no new output for STALL_MIN minutes (default 15) is flagged STALLED?
#
#   progress.sh [runs-dir]        # default: ./runs
#   STALL_MIN=10 progress.sh runs
set -u
RUNS="${1:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/runs}"
STALL_MIN="${STALL_MIN:-15}"
[ -d "$RUNS" ] || { echo "no runs dir: $RUNS" >&2; exit 2; }
mtime() { stat -f %m "$1" 2>/dev/null || stat -c %Y "$1" 2>/dev/null || echo 0; }
now=$(date +%s); total=0; finished=0
for d in "$RUNS"/*/; do
  d="${d%/}"; name="$(basename "$d")"
  [ -f "$d/prompt.txt" ] || continue
  total=$((total + 1))
  changed=$(git -C "$d/proj" status --short 2>/dev/null | wc -l | tr -d ' ')
  if [ -f "$d/meta.json" ]; then
    finished=$((finished + 1))
    python3 -I - "$d/meta.json" "$name" "$changed" <<'PY'
import json, sys
m = json.load(open(sys.argv[1]))
state = 'done' if m.get('exit') == 0 else 'ended (exit %s)' % m.get('exit')
print('%-16s %-15s %4d min  %3s tool calls  %s files changed' % (
    sys.argv[2], state, int(m.get('seconds') or 0) // 60, sum((m.get('tools') or {}).values()), sys.argv[3]))
PY
  else
    started=$(mtime "$d/prompt.txt"); last=$(mtime "$d/output.jsonl")
    [ "$last" -lt "$started" ] && last=$started
    tools=$(grep -c '"tool_use"' "$d/output.jsonl" 2>/dev/null || true)
    idle=$(( (now - last) / 60 ))
    flag=""; [ "$idle" -ge "$STALL_MIN" ] && flag="  STALLED? (no output for ${idle} min)"
    printf '%-16s %-15s %4d min  %3s tool calls  %s files changed  idle %d min%s\n' \
      "$name" "running" $(( (now - started) / 60 )) "${tools:-0}" "$changed" "$idle" "$flag"
  fi
done
echo "progress: $finished/$total finished"
