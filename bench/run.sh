#!/usr/bin/env bash
# One benchmark run: a fresh copy of the fixture, a fresh HOME, one OpenCode invocation.
#
#   run.sh <t1|t2|t3|t4> <baseline|skills> <run-index> [model]
#
# env: SUITE_DIR   folder holding install.sh + skills/ (default: this repository; or point it at a
#                  checkout of flutter-pro-skills to bench the live repo)
#      RUNS_DIR    where run folders go (default: ./runs)
#      TIMEOUT     seconds before the agent is killed (default 3600)
#      AGENT_CMD   override the agent command; it receives the prompt as its last argument and
#                  runs inside the project copy, e.g. AGENT_CMD="claude -p" (output then is plain
#                  text; save it as output.jsonl anyway, grade.py accepts plain text in .md/.txt)
#
# Isolation: HOME is a new empty directory per run, so no global skills (~/.claude/skills,
# ~/.agents/skills, ~/.config/opencode/skills), no global AGENTS.md and no prior sessions leak
# in. XDG_* are unset so they follow HOME. PUB_CACHE follows HOME too, so a `pub get` by the
# agent downloads into the temp HOME and never touches the developer's pub cache. OpenCode's
# permission config denies any access outside the project copy (external_directory: deny).
# KNOWN GAP: external_directory catches tool paths and simple bash args, but NOT shell redirects
# (`cmd > /tmp/x` succeeded in 3 of 12 runs). For strict isolation wrap the call in sandbox-exec
# (macOS) or a container with only $RUN writable.
# The fixture's pre-resolved .dart_tool points at the developer's pub cache read-only, so the
# analyzer works without network until the agent changes dependencies.
set -euo pipefail
BENCH="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TASK="${1:?task t1|t2|t3|t4}"; CONF="${2:?baseline|skills}"; IDX="${3:?run index}"
MODEL="${4:-opencode/big-pickle}"
SUITE_DIR="${SUITE_DIR:-$(cd "$BENCH/.." && pwd)}"
RUNS_DIR="${RUNS_DIR:-$BENCH/runs}"
TIMEOUT="${TIMEOUT:-3600}"

case "$TASK" in
  t1) FIX="$BENCH/fixtures/t1_mvn_shop"
      PROMPT="Review this Flutter app and list every real problem with file:line and severity." ;;
  t2) FIX="$BENCH/fixtures/t2_bloc_weather"
      PROMPT="Is this architecture correct? List violations." ;;
  t3) FIX="$BENCH/fixtures/t3_mvn_clean"
      PROMPT="Add a login feature that calls POST /login and stores the returned token, following this project's architecture." ;;
  t4) FIX="$BENCH/fixtures/t3_mvn_clean"
      PROMPT="Add a products screen that loads GET /products (each product has an id, name, price and imageUrl) and shows them in a scrollable list with each product's image, name, price and a favourite icon button, with pull-to-refresh, following this project's architecture." ;;
  *) echo "unknown task $TASK" >&2; exit 2 ;;
esac
case "$CONF" in
  baseline) ;;
  skills) PROMPT="$PROMPT Use the installed agent skills." ;;
  *) echo "unknown config $CONF" >&2; exit 2 ;;
esac

RUN="$RUNS_DIR/$TASK-$CONF-r$IDX"
rm -rf "$RUN"; mkdir -p "$RUN/home/.config/opencode"
cp -R "$FIX" "$RUN/proj"
# the agent must not see the benchmark's own notes; fixtures carry none, but be explicit
rm -rf "$RUN/proj/build"
cat > "$RUN/home/.config/opencode/opencode.json" <<'EOF'
{
  "$schema": "https://opencode.ai/config.json",
  "autoupdate": false,
  "share": "disabled",
  "permission": { "edit": "allow", "bash": "allow", "webfetch": "allow", "external_directory": "deny" }
}
EOF
if [ "$CONF" = skills ]; then
  bash "$SUITE_DIR/install.sh" --project "$RUN/proj" --agent agents > "$RUN/install.log"
fi
( cd "$RUN/proj" && git init -q . && git add -A && git -c user.email=bench@local -c user.name=bench commit -qm fixture )

printf '%s\n' "$PROMPT" > "$RUN/prompt.txt"
# TMPDIR inside the copy: external_directory is denied, so a tool told to `mktemp` would otherwise
# write somewhere the agent may not read back (this cost the first skills run its report).
mkdir -p "$RUN/proj/.bench-tmp"; echo ".bench-tmp/" >> "$RUN/proj/.git/info/exclude"
start=$(date +%s)
set +e
if [ -n "${AGENT_CMD:-}" ]; then
  ( cd "$RUN/proj" && env -u XDG_CONFIG_HOME -u XDG_DATA_HOME -u XDG_CACHE_HOME -u XDG_STATE_HOME -u PUB_CACHE \
      HOME="$RUN/home" TMPDIR="$RUN/proj/.bench-tmp" perl -e 'alarm shift; exec @ARGV' "$TIMEOUT" $AGENT_CMD "$PROMPT" ) > "$RUN/output.jsonl" 2> "$RUN/stderr.txt"
else
  ( cd "$RUN/proj" && env -u XDG_CONFIG_HOME -u XDG_DATA_HOME -u XDG_CACHE_HOME -u XDG_STATE_HOME -u PUB_CACHE \
      HOME="$RUN/home" TMPDIR="$RUN/proj/.bench-tmp" perl -e 'alarm shift; exec @ARGV' "$TIMEOUT" opencode run --format json -m "$MODEL" "$PROMPT" ) > "$RUN/output.jsonl" 2> "$RUN/stderr.txt"
fi
rc=$?
set -e
end=$(date +%s)
( cd "$RUN/proj" && git add -A >/dev/null 2>&1 && git status --short ) > "$RUN/changes.txt" 2>&1 || true
python3 -I - "$RUN" "$rc" "$((end-start))" "$MODEL" "$CONF" <<'PY'
import json, sys, re
run, rc, secs, model, conf = sys.argv[1:6]
skills, checkers, tools, steps = set(), 0, {}, 0
for line in open(run + "/output.jsonl", errors="replace"):
    try:
        ev = json.loads(line)
    except ValueError:
        continue
    if ev.get("type") == "step_finish":
        steps += 1
    if ev.get("type") != "tool_use":
        continue
    p = ev.get("part", {})
    t = p.get("tool", "?"); tools[t] = tools.get(t, 0) + 1
    inp = json.dumps(p.get("state", {}).get("input", {}))
    if t == "skill":
        m = re.search(r'"name": "([^"]+)"', inp); skills.add(m.group(1) if m else inp[:60])
    for m in re.finditer(r"\.agents/skills/([\w-]+)/SKILL\.md", inp):
        skills.add(m.group(1))
    if re.search(r"arch_check|check_errors|check_secure|check_nav|check_forms|check_i18n|review\.sh|heuristics\.py|test_gaps|scaffold\.py", inp):
        checkers += 1
json.dump({"exit": int(rc), "seconds": int(secs), "model": model, "config": conf, "steps": steps,
           "tools": tools, "skills_loaded": sorted(skills), "checker_runs": checkers},
          open(run + "/meta.json", "w"), indent=1)
PY
echo "$RUN exit=$rc secs=$((end-start))"
