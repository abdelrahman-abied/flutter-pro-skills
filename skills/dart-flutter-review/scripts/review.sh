#!/usr/bin/env bash
# Mechanical review pass for a Dart / Flutter project. READ-ONLY: never modifies the project.
#
# Usage:
#   review.sh <project-root> [--diff <git-ref>] [--no-extra] [--no-arch] [--no-tests] [--no-errors]
#             [--no-security] [--no-audit] [--no-nav] [--no-forms] [--no-i18n]
#             [--no-perf] [--no-persist] [--no-net] [--no-ds] [--no-a11y] [--skip <list>]
#             [--profile <p>] [--max <n>] [--ci] [--fail-on high|medium|low] [--baseline <file>]
#
#   --diff <ref>     only report on .dart files changed vs <ref> (committed + uncommitted + untracked)
#   --no-extra       skip the informational pass with the stricter Effective Dart lint set
#   --no-arch        skip the architecture pass (flutter-architecture/scripts/arch_check.py)
#   --no-tests       skip the test-gap pass (flutter-testing/scripts/test_gaps.py)
#   --no-errors      skip the error-handling pass (flutter-error-handling/scripts/check_errors.py)
#   --no-security    skip both security passes (SECURITY DEFAULTS and SECURITY AUDIT)
#   --no-audit       skip only the flutter-security-audit scan.sh pass
#   --no-nav / --no-forms / --no-i18n   skip the navigation / forms / i18n checker
#   --no-perf / --no-persist / --no-net / --no-ds / --no-a11y   skip the performance /
#                    persistence / networking / design-system / accessibility checker
#   --skip <list>    comma-separated sections to skip, same as the --no-* flags:
#                    extra,arch,tests,errors,security,audit,nav,forms,i18n,perf,persist,net,ds,a11y
#   --profile <p>    declared architecture for the sibling passes (auto|mvn|mvvm|bloc|mvc|getx|provider|riverpod|setstate)
#   --max <n>        max example locations printed per rule / heuristic (default 5)
#   --ci             CI mode: exit 1 on new architecture violations at or above --fail-on, or on analyzer errors
#   --fail-on <sev>  lowest architecture severity that fails --ci (default high)
#   --baseline <f>   arch_check baseline (arch-baseline@1): report only architecture violations not in it
#
# Sections: CONTEXT, FORMAT, ANALYZER (project's own config), AUTO-FIXABLE (dart fix --dry-run),
# EXTRA LINTS (../dart-flutter-best-practices/assets/analysis_options.yaml, informational),
# ARCHITECTURE (../flutter-architecture/scripts/arch_check.py: profile + import-graph/pattern violations),
# TEST GAPS (../flutter-testing/scripts/test_gaps.py), ERROR HANDLING (../flutter-error-handling/scripts/check_errors.py),
# SECURITY DEFAULTS (../flutter-secure-defaults/scripts/check_secure_defaults.py),
# SECURITY AUDIT (../flutter-security-audit/scan.sh, a separate skill; $FLUTTER_SECURITY_AUDIT_SCAN overrides the path),
# NAVIGATION, FORMS, I18N (../flutter-{navigation,forms,i18n}/scripts/check_*.py),
# PERFORMANCE, PERSISTENCE, NETWORKING, DESIGN SYSTEM, ACCESSIBILITY
# (../flutter-{performance,persistence,networking,design-system,accessibility}/scripts/check_*.py),
# CANDIDATES (heuristics: confirm by reading), CI RESULT (--ci only). Missing sibling skills are skipped, not errors.
# Only new architecture violations and analyzer errors can fail --ci; every other section is informational.
# Pub workspace members use the workspace root's .dart_tool/package_config.json. Generated files are out of
# scope (arch_check's files[] for lib/). With codegen missing, analyzer cascades are collapsed and not counted.
# With $GITHUB_STEP_SUMMARY set, a Markdown summary (section counts + top findings) is appended to it.
set -uo pipefail

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
EXTRA_OPTIONS="$SKILL_DIR/../dart-flutter-best-practices/assets/analysis_options.yaml"
ARCH_CHECK="$SKILL_DIR/../flutter-architecture/scripts/arch_check.py"
TEST_GAPS="$SKILL_DIR/../flutter-testing/scripts/test_gaps.py"
CHECK_ERRORS="$SKILL_DIR/../flutter-error-handling/scripts/check_errors.py"
CHECK_SECURE="$SKILL_DIR/../flutter-secure-defaults/scripts/check_secure_defaults.py"
CHECK_NAV="$SKILL_DIR/../flutter-navigation/scripts/check_navigation.py"
CHECK_FORMS="$SKILL_DIR/../flutter-forms/scripts/check_forms.py"
CHECK_I18N="$SKILL_DIR/../flutter-i18n/scripts/check_i18n.py"
CHECK_PERF="$SKILL_DIR/../flutter-performance/scripts/check_performance.py"
CHECK_PERSIST="$SKILL_DIR/../flutter-persistence/scripts/check_persistence.py"
CHECK_NET="$SKILL_DIR/../flutter-networking/scripts/check_networking.py"
CHECK_DS="$SKILL_DIR/../flutter-design-system/scripts/check_design_system.py"
CHECK_A11Y="$SKILL_DIR/../flutter-accessibility/scripts/check_accessibility.py"
AUDIT_SCAN="${FLUTTER_SECURITY_AUDIT_SCAN:-$SKILL_DIR/../flutter-security-audit/scan.sh}"
USAGE="usage: review.sh <project-root> [--diff <ref>] [--no-extra] [--no-arch] [--no-tests] [--no-errors] [--no-security] [--no-audit] [--no-nav] [--no-forms] [--no-i18n] [--no-perf] [--no-persist] [--no-net] [--no-ds] [--no-a11y] [--skip <list>] [--profile <p>] [--max n] [--ci] [--fail-on high|medium|low] [--baseline <file>]"
ROOT=""; DIFF_REF=""; EXTRA=1; ARCH=1; TESTS=1; ERRORS=1; SECURE=1; AUDIT=1; NAV=1; FORMS=1; I18N=1
PERF=1; PERSIST=1; NET=1; DS=1; A11Y=1
PROFILE=""; MAX=5; CI=0; FAIL_ON=high; BASELINE=""
needs() { [[ -n "${2:-}" ]] || { echo "error: $1 needs a value" >&2; echo "$USAGE" >&2; exit 2; }; }
skip_one() {
  case "$1" in
    extra) EXTRA=0 ;; arch) ARCH=0 ;; tests) TESTS=0 ;; errors) ERRORS=0 ;;
    security) SECURE=0; AUDIT=0 ;; audit) AUDIT=0 ;; nav|navigation) NAV=0 ;; forms) FORMS=0 ;; i18n) I18N=0 ;;
    perf|performance) PERF=0 ;; persist|persistence) PERSIST=0 ;; net|networking) NET=0 ;; ds|design-system) DS=0 ;; a11y|accessibility) A11Y=0 ;;
    *) echo "error: --skip: unknown section '$1' (extra,arch,tests,errors,security,audit,nav,forms,i18n,perf,persist,net,ds,a11y)" >&2; exit 2 ;;
  esac
}
while [[ $# -gt 0 ]]; do
  case "$1" in
    --diff|--profile|--max|--fail-on|--baseline|--skip) needs "$1" "${2:-}" ;;
  esac
  case "$1" in
    --diff) DIFF_REF="$2"; shift 2 ;;
    --no-extra) EXTRA=0; shift ;;
    --no-arch) ARCH=0; shift ;;
    --no-tests) TESTS=0; shift ;;
    --no-errors) ERRORS=0; shift ;;
    --no-security) SECURE=0; AUDIT=0; shift ;;
    --no-audit) AUDIT=0; shift ;;
    --no-nav) NAV=0; shift ;;
    --no-forms) FORMS=0; shift ;;
    --no-i18n) I18N=0; shift ;;
    --no-perf) PERF=0; shift ;;
    --no-persist) PERSIST=0; shift ;;
    --no-net) NET=0; shift ;;
    --no-ds) DS=0; shift ;;
    --no-a11y) A11Y=0; shift ;;
    --skip) for k in $(echo "$2" | tr ',' ' '); do skip_one "$k"; done; shift 2 ;;
    --profile) PROFILE="$2"; shift 2 ;;
    --max) MAX="$2"; shift 2 ;;
    --ci) CI=1; shift ;;
    --fail-on) FAIL_ON="$2"; shift 2 ;;
    --baseline) BASELINE="$2"; shift 2 ;;
    -h|--help) sed -n '2,/^set -uo/p' "$0" | sed '$d'; exit 0 ;;
    -*) echo "error: unknown option $1" >&2; echo "$USAGE" >&2; exit 2 ;;
    *) ROOT="$1"; shift ;;
  esac
done
[[ -n "$ROOT" ]] || { echo "$USAGE" >&2; exit 2; }
case "$FAIL_ON" in high|medium|low) ;; *) echo "error: --fail-on must be high, medium or low" >&2; exit 2 ;; esac
if [[ -n "$BASELINE" ]]; then
  [[ -f "$BASELINE" ]] || { echo "error: --baseline file not found: $BASELINE" >&2; exit 2; }
  BASELINE="$(cd "$(dirname "$BASELINE")" && pwd)/$(basename "$BASELINE")"
fi
ROOT="$(cd "$ROOT" && pwd)" || exit 2
[[ -f "$ROOT/pubspec.yaml" ]] || { echo "error: no pubspec.yaml in $ROOT" >&2; exit 2; }
command -v dart >/dev/null || { echo "error: dart not on PATH" >&2; exit 2; }

WORK="$(mktemp -d "${TMPDIR:-/tmp}/dart-review.XXXXXX")"
trap 'rm -rf "$WORK"' EXIT
SEC="$WORK/sections"; mkdir -p "$SEC"   # each section's output, for the step summary and the CI verdict

# ---- file scope -------------------------------------------------------------
if [[ -n "$DIFF_REF" ]]; then
  { git -C "$ROOT" diff --name-only --diff-filter=ACMR "$DIFF_REF" -- '*.dart'
    git -C "$ROOT" ls-files --others --exclude-standard --full-name -- '*.dart'; } 2>/dev/null \
    | sort -u > "$WORK/files.raw"
  # git paths are relative to the repo root; make them relative to ROOT.
  # --show-prefix is symlink-safe (e.g. macOS /var -> /private/var), unlike stripping --show-toplevel.
  PREFIX="$(git -C "$ROOT" rev-parse --show-prefix 2>/dev/null)"; PREFIX="${PREFIX%/}"
  while IFS= read -r f; do
    [[ -z "$f" ]] && continue
    rel="$f"; [[ -n "$PREFIX" ]] && { [[ "$f" == "$PREFIX/"* ]] || continue; rel="${f#"$PREFIX/"}"; }
    [[ -f "$ROOT/$rel" ]] && echo "$rel"
  done < "$WORK/files.raw" > "$WORK/files.all"
else
  (cd "$ROOT" && find lib test bin tool integration_test -name '*.dart' -type f 2>/dev/null) | sort > "$WORK/files.all"
fi
# Generated files are out of scope. arch_check's files[] is the source of truth for lib/ (it knows
# *.gen.dart, l10n output-dir, "GENERATED CODE" headers ...); heuristics.py applies the same rules elsewhere.
ARCH_JSON=""
if [[ -f "$ARCH_CHECK" ]]; then
  ARCH_PROFILE_ARGS=""; [[ -n "$PROFILE" ]] && ARCH_PROFILE_ARGS="--profile $PROFILE"
  # shellcheck disable=SC2086
  if python3 -I "$ARCH_CHECK" "$ROOT" --json $ARCH_PROFILE_ARGS > "$WORK/arch_scope.json" 2> /dev/null; then ARCH_JSON="$WORK/arch_scope.json"; fi
fi
# Computed once; every sibling checker reuses it instead of re-running arch_check (CONTRACTS §19).
[[ -n "$ARCH_JSON" ]] && export FPS_ARCH_JSON="$ARCH_JSON"
python3 -I "$SKILL_DIR/scripts/heuristics.py" scope "$ROOT" "$WORK/files.all" "$ARCH_JSON" > "$WORK/files" || cp "$WORK/files.all" "$WORK/files"
NFILES=$(wc -l < "$WORK/files" | tr -d ' ')

SDK="$(dart --version 2>&1 | sed -E 's/.*version: ([^ ]+).*/\1/')"
# is_flutter, sdk constraint, lint include(s), sdk status, package_config path, note (TSV; '-' = empty).
# Parsed in Python: BSD sed has no \s, and `include:` may be a YAML list.
IFS=$'\t' read -r IS_FLUTTER CONSTRAINT INCLUDE SDK_STATUS PKG_CONFIG PKG_NOTE \
  < <(python3 -I "$SKILL_DIR/scripts/heuristics.py" context "$ROOT" "$SDK")
for v in CONSTRAINT INCLUDE SDK_STATUS PKG_CONFIG PKG_NOTE; do [[ "${!v}" == - ]] && printf -v "$v" '%s' ''; done
[[ "$IS_FLUTTER" == 1 ]] || IS_FLUTTER=0
SDK_OK=1; [[ -n "$SDK_STATUS" && "$SDK_STATUS" != ok ]] && SDK_OK=0

echo "== CONTEXT"
echo "project:        $ROOT"
echo "type:           $([[ $IS_FLUTTER == 1 ]] && echo Flutter app/package || echo Dart package)"
echo "dart sdk:       $SDK   pubspec constraint: ${CONSTRAINT:-?}"
echo "lint include:   ${INCLUDE:-<none — no analysis_options.yaml or no include>}"
echo "scope:          $([[ -n "$DIFF_REF" ]] && echo "diff vs $DIFF_REF" || echo "whole project") — $NFILES non-generated .dart files"
[[ -n "$PKG_NOTE" ]] && echo "packages:       $PKG_NOTE"
if [[ $SDK_OK == 0 ]]; then
  echo "WARNING: $SDK_STATUS — ANALYZER, AUTO-FIXABLE and EXTRA LINTS are skipped (their output would be SDK-mismatch noise). Use a matching SDK."
elif [[ -z "$PKG_CONFIG" ]]; then
  echo "WARNING: no .dart_tool/package_config.json (here or in a pub workspace root) — run 'dart pub get' / 'flutter pub get' first; analyzer results will be mostly unresolved-import errors."
fi
echo
SCOPE_DESC="$([[ -n "$DIFF_REF" ]] && echo "diff vs \`$DIFF_REF\`" || echo "whole project") — $NFILES .dart files"
if [[ "$NFILES" -eq 0 ]]; then
  echo "No Dart files in scope."
  if [[ -n "${GITHUB_STEP_SUMMARY:-}" ]]; then
    printf '## Flutter review\n\nScope: %s\n\nNo Dart files in scope.\n' "$SCOPE_DESC" >> "$GITHUB_STEP_SUMMARY"
  fi
  exit 0
fi

# ---- FORMAT -----------------------------------------------------------------
{
echo "== FORMAT (dart format, check only)"
(cd "$ROOT" && tr '\n' '\0' < "$WORK/files" | xargs -0 dart format --output=none --set-exit-if-changed 2>&1) \
  | grep -E '^Changed ' | sed 's/^Changed /  needs format: /' > "$WORK/format.txt" || true
if [[ -s "$WORK/format.txt" ]]; then
  echo "  $(wc -l < "$WORK/format.txt" | tr -d ' ') file(s) not formatted:"; head -n "$MAX" "$WORK/format.txt"
else echo "  all formatted"; fi
} | tee "$SEC/format.txt"
echo

# ---- ANALYZER (project config) ----------------------------------------------
: > "$WORK/analyze.txt"
if [[ $SDK_OK == 0 ]]; then
  echo "== ANALYZER (skipped: $SDK_STATUS)" | tee "$SEC/analyzer.txt"
  : > "$SEC/analyzer.unresolved"
else
  {
  echo "== ANALYZER (project's own analysis_options)"
  (cd "$ROOT" && dart analyze --format=machine . > "$WORK/analyze.txt" 2>&1) || true
  python3 -I "$SKILL_DIR/scripts/heuristics.py" analyzer "$ROOT" "$WORK/files" "$WORK/analyze.txt" "$MAX"
  } | tee "$SEC/analyzer.txt"
  [[ -n "$PKG_CONFIG" ]] || : > "$SEC/analyzer.unresolved"
fi
echo

# ---- AUTO-FIXABLE -----------------------------------------------------------
if [[ $SDK_OK == 0 ]]; then
  echo "== AUTO-FIXABLE (skipped: $SDK_STATUS)" | tee "$SEC/fix.txt"
else
  {
  echo "== AUTO-FIXABLE (dart fix --dry-run; nothing applied)"
  (cd "$ROOT" && dart fix --dry-run > "$WORK/fix.txt" 2>&1) || true
  python3 -I "$SKILL_DIR/scripts/heuristics.py" fix "$ROOT" "$WORK/files" "$WORK/fix.txt" "$MAX"
  } | tee "$SEC/fix.txt"
fi
echo

# ---- EXTRA LINTS (informational) --------------------------------------------
if [[ $EXTRA == 1 && ! -f "$EXTRA_OPTIONS" ]]; then
  echo "== EXTRA LINTS (skipped: dart-flutter-best-practices skill not installed next to this one)"
  echo
elif [[ $EXTRA == 1 && $SDK_OK == 0 ]]; then
  echo "== EXTRA LINTS (skipped: $SDK_STATUS)"
  echo
elif [[ $EXTRA == 1 && -z "$PKG_CONFIG" ]]; then
  echo "== EXTRA LINTS (skipped: packages not resolved; run pub get first)"
  echo
elif [[ $EXTRA == 1 ]]; then
  echo "== EXTRA LINTS (Effective Dart set from dart-flutter-best-practices/assets/analysis_options.yaml — informational, project has NOT opted in)"
  mkdir -p "$WORK/copy"
  # copy every .dart file (generated code too, so parts/providers resolve); reporting is still limited to scope
  (cd "$ROOT" && find lib test bin tool integration_test -name '*.dart' -type f 2>/dev/null \
     | tr '\n' '\0' | xargs -0 -I{} rsync -R "{}" "$WORK/copy/" 2>/dev/null)
  # a workspace member's `resolution: workspace` would make the copy look for a workspace root that isn't there;
  # --packages already points at the resolved config
  grep -Ev '^resolution:' "$ROOT/pubspec.yaml" > "$WORK/copy/pubspec.yaml"
  python3 -I "$SKILL_DIR/scripts/heuristics.py" mkoptions "$ROOT" "$EXTRA_OPTIONS" "$WORK/copy/analysis_options.yaml" "$IS_FLUTTER" "$PKG_CONFIG"
  (cd "$WORK/copy" && dart analyze --format=machine --packages="$PKG_CONFIG" . > "$WORK/extra.txt" 2>&1) || true
  python3 -I "$SKILL_DIR/scripts/heuristics.py" extra "$WORK/copy" "$WORK/files" "$WORK/extra.txt" "$MAX" "$WORK/analyze.txt" "$EXTRA_OPTIONS"
  echo
fi

# ---- sibling skill passes ----------------------------------------------------
# run_sibling <section-key> <HEADER> <script> <skill-name> <args...>
# The sibling prints its own "== ..." header(s); if it does not, HEADER is printed for it.
# Exit 1 is accepted only from arch_check in --ci mode (= new violations at or above --fail-on).
SIB_RC=0
run_sibling() {
  local key="$1" header="$2" script="$3" skill="$4"; shift 4
  SIB_RC=0
  if [[ ! -f "$script" ]]; then
    echo "== $header (skipped: $skill skill not installed)" | tee "$SEC/$key.txt"
    echo; return
  fi
  python3 -I "$script" "$@" > "$WORK/$key.out" 2> "$WORK/$key.err"; SIB_RC=$?
  if [[ $SIB_RC == 0 || ( $SIB_RC == 1 && $key == arch && $CI == 1 ) ]]; then
    {
      head -n 1 "$WORK/$key.out" | grep -q '^== ' || echo "== $header"
      if [[ -n "${SIB_NOTE:-}" ]]; then
        awk -v n="$SIB_NOTE" 'NR == 1 && /^== / {print; print n; next} NR == 1 {print n} {print}' "$WORK/$key.out"
      else cat "$WORK/$key.out"; fi
    } | tee "$SEC/$key.txt"
  else
    { echo "== $header (error: $(basename "$script") exited $SIB_RC)"
      cat "$WORK/$key.out" "$WORK/$key.err" | sed 's/^/  /' | head -n 20; } | tee "$SEC/$key.txt"
  fi
  echo
}

# ---- ARCHITECTURE (flutter-architecture skill) ------------------------------
ARCH_RC=0
if [[ $ARCH == 1 ]]; then
  ARCH_ARGS=("$ROOT" --max "$MAX")
  [[ -n "$DIFF_REF" ]] && ARCH_ARGS+=(--files "$WORK/files")
  [[ -n "$PROFILE" ]] && ARCH_ARGS+=(--profile "$PROFILE")
  [[ -n "$BASELINE" ]] && ARCH_ARGS+=(--baseline "$BASELINE")
  [[ $CI == 1 ]] && ARCH_ARGS+=(--ci --fail-on "$FAIL_ON")
  SIB_NOTE="" run_sibling arch "ARCHITECTURE" "$ARCH_CHECK" flutter-architecture "${ARCH_ARGS[@]}"
  ARCH_RC=$SIB_RC
fi

# ---- TEST GAPS (flutter-testing skill) --------------------------------------
if [[ $TESTS == 1 ]]; then
  TG_ARGS=("$ROOT" --max "$MAX")
  [[ -n "$PROFILE" ]] && TG_ARGS+=(--profile "$PROFILE")
  NOTE=""; [[ -n "$DIFF_REF" ]] && NOTE="  note: whole project (test_gaps.py has no diff scope)"
  SIB_NOTE="$NOTE" run_sibling tests "TEST GAPS" "$TEST_GAPS" flutter-testing "${TG_ARGS[@]}"
fi

# ---- ERROR HANDLING (flutter-error-handling skill) --------------------------
ERR_RAN=0
if [[ $ERRORS == 1 ]]; then
  CE_ARGS=("$ROOT" --max "$MAX")
  [[ -n "$DIFF_REF" ]] && CE_ARGS+=(--files "$WORK/files")
  [[ -n "$PROFILE" ]] && CE_ARGS+=(--profile "$PROFILE")
  SIB_NOTE="" run_sibling errors "ERROR HANDLING" "$CHECK_ERRORS" flutter-error-handling "${CE_ARGS[@]}"
  [[ -f "$CHECK_ERRORS" && $SIB_RC == 0 ]] && ERR_RAN=1
fi

# ---- SECURITY DEFAULTS, NAVIGATION, FORMS, I18N (CONTRACTS §14/§17 checkers) --
# Same CLI for all four: <root> [--files <list>] [--profile <p>] [--max n]; informational, never fail CI.
checker_args() {
  CK_ARGS=("$ROOT" --max "$MAX")
  [[ -n "$DIFF_REF" ]] && CK_ARGS+=(--files "$WORK/files")
  [[ -n "$PROFILE" ]] && CK_ARGS+=(--profile "$PROFILE")
}
checker_args
[[ $SECURE == 1 ]] && SIB_NOTE="" run_sibling secure "SECURITY DEFAULTS" "$CHECK_SECURE" flutter-secure-defaults "${CK_ARGS[@]}"

# ---- SECURITY AUDIT (flutter-security-audit scan.sh: separate skill, deeper MASVS/CWE sweep) ----
# scan.sh exits 1 on Critical/High by design (its own CI gate); here it is informational only.
if [[ $AUDIT == 1 ]]; then
  if [[ ! -f "$AUDIT_SCAN" ]]; then
    echo "== SECURITY AUDIT (skipped: flutter-security-audit skill not installed)" | tee "$SEC/audit.txt"
  else
    bash "$AUDIT_SCAN" "$ROOT" --json > "$WORK/audit.json" 2> "$WORK/audit.err"; AUDIT_RC=$?
    if [[ $AUDIT_RC == 0 || $AUDIT_RC == 1 ]]; then
      { echo "== SECURITY AUDIT (flutter-security-audit scan.sh — candidates, informational, never fails CI)"
        python3 -I "$SKILL_DIR/scripts/heuristics.py" audit "$ROOT" "$([[ -n "$DIFF_REF" ]] && echo "$WORK/files" || echo -)" \
          "$WORK/audit.json" "$MAX"; } | tee "$SEC/audit.txt"
    else
      { echo "== SECURITY AUDIT (error: scan.sh exited $AUDIT_RC)"
        cat "$WORK/audit.json" "$WORK/audit.err" | sed 's/^/  /' | head -n 20; } | tee "$SEC/audit.txt"
    fi
  fi
  echo
fi

[[ $NAV == 1 ]] && SIB_NOTE="" run_sibling nav "NAVIGATION" "$CHECK_NAV" flutter-navigation "${CK_ARGS[@]}"
[[ $FORMS == 1 ]] && SIB_NOTE="" run_sibling forms "FORMS" "$CHECK_FORMS" flutter-forms "${CK_ARGS[@]}"
[[ $I18N == 1 ]] && SIB_NOTE="" run_sibling i18n "I18N" "$CHECK_I18N" flutter-i18n "${CK_ARGS[@]}"

# ---- PERFORMANCE, PERSISTENCE, DESIGN SYSTEM, ACCESSIBILITY (CONTRACTS §21-§25 checkers) ----
PERF_RAN=0; DS_RAN=0
if [[ $PERF == 1 ]]; then
  SIB_NOTE="" run_sibling perf "PERFORMANCE" "$CHECK_PERF" flutter-performance "${CK_ARGS[@]}"
  [[ -f "$CHECK_PERF" && $SIB_RC == 0 ]] && PERF_RAN=1
fi
[[ $PERSIST == 1 ]] && SIB_NOTE="" run_sibling persist "PERSISTENCE" "$CHECK_PERSIST" flutter-persistence "${CK_ARGS[@]}"
[[ $NET == 1 ]] && SIB_NOTE="" run_sibling net "NETWORKING" "$CHECK_NET" flutter-networking "${CK_ARGS[@]}"
if [[ $DS == 1 ]]; then
  SIB_NOTE="" run_sibling ds "DESIGN SYSTEM" "$CHECK_DS" flutter-design-system "${CK_ARGS[@]}"
  [[ -f "$CHECK_DS" && $SIB_RC == 0 ]] && DS_RAN=1
fi
[[ $A11Y == 1 ]] && SIB_NOTE="" run_sibling a11y "ACCESSIBILITY" "$CHECK_A11Y" flutter-accessibility "${CK_ARGS[@]}"

# ---- CANDIDATES (heuristics) ------------------------------------------------
# swallowed-catch overlaps check_errors.py's swallowed-catch rule: when that ran, keep only the
# count here and point at ERROR HANDLING, so the same catch is not reported twice. Likewise
# eager-children-map / opacity-widget defer to PERFORMANCE and hardcoded-color to DESIGN SYSTEM (§23).
DEFER=""; [[ $ERR_RAN == 1 ]] && DEFER="defer-catch"
[[ $PERF_RAN == 1 ]] && DEFER="$DEFER defer-perf"
[[ $DS_RAN == 1 ]] && DEFER="$DEFER defer-ds"
{
echo "== CANDIDATES (heuristic — confirm each by reading the code before reporting)"
python3 -I "$SKILL_DIR/scripts/heuristics.py" grep "$ROOT" "$WORK/files" "$MAX" "$IS_FLUTTER" $DEFER
} | tee "$SEC/candidates.txt"

# ---- CI verdict + step summary ----------------------------------------------
RC=0
if [[ $CI == 1 ]]; then
  read -r ANALYZER_ERRORS CASCADE_ERRORS ANALYZER_CRASHED \
    < <(python3 -I "$SKILL_DIR/scripts/heuristics.py" errors "$ROOT" "$WORK/files" "$WORK/analyze.txt")
  CASC=""; [[ "${CASCADE_ERRORS:-0}" -gt 0 ]] && CASC="; $CASCADE_ERRORS likely codegen-cascade error(s) not counted: run build_runner first"
  echo
  echo "== CI RESULT (fail-on: $FAIL_ON)"
  if [[ $ARCH == 0 ]]; then
    echo "  architecture: skipped (--no-arch)"
  elif [[ ! -f "$ARCH_CHECK" ]]; then
    echo "  architecture: skipped (flutter-architecture skill not installed)"
  elif [[ $ARCH_RC == 1 ]]; then
    echo "  architecture: FAIL — $(grep -E '^  ci: ' "$SEC/arch.txt" | sed -e 's/^  ci: fail (//' -e 's/)$//' -e 's/ at or above/ new at or above/')"; RC=1
  elif [[ $ARCH_RC != 0 ]]; then
    echo "  architecture: ERROR — arch_check.py exited $ARCH_RC"; RC=1
  else
    echo "  architecture: pass ($(grep -E '^  summary: ' "$SEC/arch.txt" | sed 's/^  summary: //'))"
  fi
  if [[ $SDK_OK == 0 ]]; then
    echo "  analyzer: not counted (skipped: $SDK_STATUS)"
  elif [[ -z "$PKG_CONFIG" ]]; then
    echo "  analyzer: not counted ($ANALYZER_ERRORS error(s), but no pub get: unresolved imports are noise)"
  elif [[ "${ANALYZER_CRASHED:-0}" == 1 && "$ANALYZER_ERRORS" -eq 0 ]]; then
    echo "  analyzer: not counted (the analyzer crashed; see ANALYZER)"
  elif [[ "$ANALYZER_ERRORS" -gt 0 ]]; then
    echo "  analyzer: FAIL — $ANALYZER_ERRORS error(s) in scope$CASC"; RC=1
  else
    echo "  analyzer: pass (0 errors in scope$CASC)"
  fi
  echo "  test gaps, error handling, security, navigation, forms, i18n, performance, persistence, networking, design system, accessibility, candidates: informational (never fail CI)"
  echo "  result: $([[ $RC == 1 ]] && echo "FAIL (exit 1)" || echo "pass")"
fi
if [[ -n "${GITHUB_STEP_SUMMARY:-}" ]]; then
  python3 -I "$SKILL_DIR/scripts/heuristics.py" summary "$SEC" "$SCOPE_DESC" "$CI" "$FAIL_ON" "$RC" >> "$GITHUB_STEP_SUMMARY" \
    || echo "warning: could not write \$GITHUB_STEP_SUMMARY" >&2
fi
exit $RC
