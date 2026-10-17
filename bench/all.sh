#!/usr/bin/env bash
# Run the full matrix (3 tasks x {baseline, skills} x N runs), PAR at a time, then print the table.
#   N=2 PAR=4 MODEL=opencode/big-pickle SUITE_DIR=/path/to/flutter-pro-skills RUNS_DIR=./runs ./all.sh
set -u
BENCH="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
N="${N:-2}"; PAR="${PAR:-4}"; MODEL="${MODEL:-opencode/big-pickle}"
jobs_list=""
for i in $(seq 1 "$N"); do for t in t1 t2 t3; do for c in baseline skills; do jobs_list="$jobs_list $t:$c:$i"; done; done; done
for j in $jobs_list; do
  while [ "$(jobs -rp | wc -l)" -ge "$PAR" ]; do sleep 5; done
  IFS=: read -r t c i <<< "$j"
  "$BENCH/run.sh" "$t" "$c" "$i" "$MODEL" &
done
wait
python3 -I "$BENCH/grade.py" summary "${RUNS_DIR:-$BENCH/runs}"
