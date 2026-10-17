#!/usr/bin/env bash
# Entry point of the root action.yml (composite GitHub Action). READ-ONLY towards the project.
# Also runnable locally: set the INPUT_* variables and run it from the repository root.
#
#   INPUT_PATH       project root, relative to the current directory (default .)
#   INPUT_BASE_REF   git ref to diff against (e.g. origin/main); empty = whole project
#   INPUT_FAIL_ON    high|medium|low (default high)
#   INPUT_BASELINE   arch-baseline@1 file (optional), relative to the current directory
#   INPUT_FLUTTER    true = full review.sh --ci (needs dart/flutter on PATH, deps fetched);
#                    false = arch_check.py --ci only (needs python3 only)
#
# Writes the report to $REPORT_DIR (default $RUNNER_TEMP or $TMPDIR)/flutter-pro-skills-report.txt,
# appends Markdown to $GITHUB_STEP_SUMMARY and new-violations / report-path to $GITHUB_OUTPUT
# when those are set. Exit: 0 pass, 1 CI failure, 2 usage/environment error.
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILLS="$(cd "$HERE/../.." && pwd)"
ARCH_CHECK="$SKILLS/flutter-architecture/scripts/arch_check.py"
REVIEW="$SKILLS/dart-flutter-review/scripts/review.sh"

ROOT="${INPUT_PATH:-.}"
BASE_REF="${INPUT_BASE_REF:-}"
FAIL_ON="${INPUT_FAIL_ON:-high}"
BASELINE="${INPUT_BASELINE:-}"
FLUTTER="$(echo "${INPUT_FLUTTER:-false}" | tr '[:upper:]' '[:lower:]')"
OUT_DIR="${REPORT_DIR:-${RUNNER_TEMP:-${TMPDIR:-/tmp}}}"
REPORT="${OUT_DIR%/}/flutter-pro-skills-report.txt"

case "$FAIL_ON" in high|medium|low) ;; *) echo "::error::fail-on must be high, medium or low (got '$FAIL_ON')"; exit 2 ;; esac
case "$FLUTTER" in true|false) ;; *) echo "::error::flutter must be true or false (got '$FLUTTER')"; exit 2 ;; esac
[[ -f "$ROOT/pubspec.yaml" ]] || { echo "::error::no pubspec.yaml in '$ROOT' (set the path input)"; exit 2; }
ROOT="$(cd "$ROOT" && pwd)"
if [[ -n "$BASELINE" ]]; then
  [[ -f "$BASELINE" ]] || { echo "::error::baseline file not found: $BASELINE"; exit 2; }
  BASELINE="$(cd "$(dirname "$BASELINE")" && pwd)/$(basename "$BASELINE")"
fi
mkdir -p "$OUT_DIR"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/fps-action.XXXXXX")"
trap 'rm -rf "$WORK"' EXIT

# Diff against the merge base when it is reachable, so changes that landed on the base
# branch after this branch forked are not counted as this PR's (needs fetch-depth: 0).
DIFF=""
if [[ -n "$BASE_REF" ]]; then
  if ! git -C "$ROOT" rev-parse --verify --quiet "$BASE_REF^{commit}" > /dev/null; then
    git -C "$ROOT" fetch --no-tags --quiet origin "${BASE_REF#origin/}" 2> /dev/null \
      && BASE_REF_RESOLVED=FETCH_HEAD || BASE_REF_RESOLVED=""
  else BASE_REF_RESOLVED="$BASE_REF"; fi
  [[ -n "$BASE_REF_RESOLVED" ]] || { echo "::error::base-ref '$BASE_REF' not found; check out with fetch-depth: 0"; exit 2; }
  DIFF="$(git -C "$ROOT" merge-base "$BASE_REF_RESOLVED" HEAD 2> /dev/null || echo "$BASE_REF_RESOLVED")"
fi

if [[ "$FLUTTER" == true ]]; then
  ARGS=("$ROOT" --ci --fail-on "$FAIL_ON")
  [[ -n "$BASELINE" ]] && ARGS+=(--baseline "$BASELINE")
  [[ -n "$DIFF" ]] && ARGS+=(--diff "$DIFF")
  bash "$REVIEW" "${ARGS[@]}" 2>&1 | tee "$REPORT"; RC=${PIPESTATUS[0]}
else
  ARGS=("$ROOT" --ci --fail-on "$FAIL_ON")
  [[ -n "$BASELINE" ]] && ARGS+=(--baseline "$BASELINE")
  SCOPE="whole project"
  if [[ -n "$DIFF" ]]; then
    git -C "$ROOT" diff --name-only --relative --diff-filter=ACMR "$DIFF" -- '*.dart' > "$WORK/files" 2> /dev/null
    ARGS+=(--files "$WORK/files")
    SCOPE="diff vs \`$BASE_REF\` — $(wc -l < "$WORK/files" | tr -d ' ') changed .dart files"
  fi
  python3 -I "$ARCH_CHECK" "${ARGS[@]}" 2>&1 | tee "$REPORT"; RC=${PIPESTATUS[0]}
  if [[ -n "${GITHUB_STEP_SUMMARY:-}" ]]; then
    mkdir -p "$WORK/sections"; cp "$REPORT" "$WORK/sections/arch.txt"
    python3 -I "$HERE/heuristics.py" summary "$WORK/sections" "$SCOPE" 1 "$FAIL_ON" "$RC" arch-only >> "$GITHUB_STEP_SUMMARY"
  fi
fi

NEW="$(grep -E '^  summary: [0-9]+ new' "$REPORT" | head -1 | sed -E 's/^  summary: ([0-9]+) new.*/\1/')"
if [[ -n "${GITHUB_OUTPUT:-}" ]]; then
  echo "new-violations=${NEW:-0}" >> "$GITHUB_OUTPUT"
  echo "report-path=$REPORT" >> "$GITHUB_OUTPUT"
fi
echo "flutter-pro-skills: ${NEW:-0} new architecture violation(s); report at $REPORT; exit $RC"
exit "$RC"
