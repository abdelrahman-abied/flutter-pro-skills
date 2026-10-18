#!/usr/bin/env bash
# Tests for flutter-adaptive-layout/scripts/check_adaptive.py.
# No Flutter SDK or pub get needed: the checker is static. bash 3.2 compatible.
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL="$(cd "$HERE/.." && pwd)"
CHECK="$SKILL/scripts/check_adaptive.py"
FIX="$HERE/fixtures"
TMP="$(mktemp -d "${TMPDIR:-/tmp}/adaptcheck.XXXXXX")"
trap 'rm -rf "$TMP"' EXIT
fail=0

pass() { echo "PASS $1"; }
bad() { echo "FAIL $1"; fail=1; }

# assert <name> <json-file> <python-expression over d (the report) and ids (set of rule ids)>
assert() {
  local name="$1" file="$2" expr="$3"
  if python3 -I - "$file" "$expr" <<'PY'
import json, sys
d = json.load(open(sys.argv[1]))
ids = {f['id'] for f in d['findings']}
def at(rel, line, rid):
    return [f for f in d['findings'] if f['file'] == rel and f['line'] == line and f['id'] == rid]
def of(rid):
    return [f for f in d['findings'] if f['id'] == rid]
def infile(rel):
    return [f for f in d['findings'] if f['file'] == rel]
ok = eval(sys.argv[2])
if not ok:
    sys.stderr.write('    expression was false: %s\n' % sys.argv[2])
    sys.stderr.write('    findings: %s\n' % sorted((f['id'], f['severity'], f['file'], f['line']) for f in d['findings']))
sys.exit(0 if ok else 1)
PY
  then pass "$name"; else bad "$name"; fi
}

checksum() { (cd "$1" && find . -type f | LC_ALL=C sort | while read -r f; do cksum "$f"; done); }

# --- syntax: stays Python 3.8 compatible
if python3 -I -c "import ast,sys; ast.parse(open(sys.argv[1]).read(), feature_version=(3, 8))" "$CHECK" 2>/dev/null; then
  pass "check_adaptive.py parses as Python 3.8"
else
  bad "check_adaptive.py parses as Python 3.8"
fi

# --- violations fixture: every rule fires
before="$(checksum "$FIX/violations")"
python3 -I "$CHECK" "$FIX/violations" --json > "$TMP/v.json"; rc=$?
[ $rc = 0 ] && pass "violations: exit 0 with findings" || bad "violations: exit 0 with findings (got $rc)"
after="$(checksum "$FIX/violations")"
[ "$before" = "$after" ] && pass "read-only: fixture unchanged" || bad "read-only: fixture unchanged"
for n in 001 002 003 004 005 006 007 008 009 010; do
  assert "violations: ADAPT-$n triggered" "$TMP/v.json" "'ADAPT-$n' in ids"
done
VIEW=lib/features/catalog/presentation/view/catalog_view.dart
NOTI=lib/features/catalog/presentation/notifier/catalog_notifier.dart
TILE=lib/features/catalog/presentation/widgets/catalog_tile.dart
DEV=lib/core/device/device_kind.dart
assert "ADAPT-001 high in a widget and in a notifier of a web app" "$TMP/v.json" "at('$VIEW', 13, 'ADAPT-001')[0]['severity'] == 'high' and at('$NOTI', 13, 'ADAPT-001')[0]['severity'] == 'high' and len(of('ADAPT-001')) == 2"
assert "ADAPT-001 note carries the MVN placement"            "$TMP/v.json" "all('MVN:' in f['note'] for f in of('ADAPT-001'))"
assert "ADAPT-002 low for a kIsWeb-guarded widget check, not 001" "$TMP/v.json" "at('$VIEW', 34, 'ADAPT-002')[0]['severity'] == 'low' and not at('$VIEW', 34, 'ADAPT-001')"
assert "ADAPT-002 is not reported for a non-UI file"         "$TMP/v.json" "not infile('$DEV') or 'ADAPT-002' not in {f['id'] for f in infile('$DEV')}"
assert "ADAPT-003 medium in main() of a mobile app"          "$TMP/v.json" "at('lib/main.dart', 9, 'ADAPT-003')[0]['severity'] == 'medium'"
assert "ADAPT-004 two literal breakpoints in two files"      "$TMP/v.json" "[(f['file'], f['line']) for f in of('ADAPT-004')] == [('$VIEW', 19), ('$TILE', 15)] and 'MVN:' in of('ADAPT-004')[0]['note'] and '600, 840' in of('ADAPT-004')[0]['note']"
assert "ADAPT-005 medium: model name and platform-only isPhone" "$TMP/v.json" "[f['line'] for f in of('ADAPT-005')] == [7, 10] and all(f['severity'] == 'medium' for f in of('ADAPT-005'))"
assert "ADAPT-006 low: orientation picks the layout"         "$TMP/v.json" "at('$VIEW', 14, 'ADAPT-006')[0]['severity'] == 'low'"
assert "ADAPT-007 medium: isTablet field in a notifier, MVN note" "$TMP/v.json" "at('$NOTI', 9, 'ADAPT-007')[0]['severity'] == 'medium' and 'MVN:' in at('$NOTI', 9, 'ADAPT-007')[0]['note']"
assert "ADAPT-008 medium: hover-only delete button"          "$TMP/v.json" "at('$TILE', 22, 'ADAPT-008')[0]['severity'] == 'medium' and '_hovered' in at('$TILE', 22, 'ADAPT-008')[0]['note']"
assert "ADAPT-009 low at runApp, names the desktop platform" "$TMP/v.json" "at('lib/main.dart', 10, 'ADAPT-009') and 'macos' in at('lib/main.dart', 10, 'ADAPT-009')[0]['note']"
assert "ADAPT-010 low in a test without reset"               "$TMP/v.json" "at('test/catalog_view_test.dart', 7, 'ADAPT-010')[0]['severity'] == 'low' and 'tester.view.reset' in of('ADAPT-010')[0]['note']"
assert "uses arch_check files[] when installed"              "$TMP/v.json" "d['classification'] == 'arch_check files[]' or d['classification'].startswith('path-based fallback (flutter-architecture')"

# --- JSON contract (CONTRACTS §22, §34)
assert "JSON: schema and top-level keys" "$TMP/v.json" "d['schema'] == 'flutter-pro-skills/adaptive-layout@1' and set(d) >= {'schema','root','package','profile','classification','stats','findings','suppressed'}"
assert "JSON: finding keys"              "$TMP/v.json" "all(set(f) == {'id','name','severity','file','line','evidence','message','note'} for f in d['findings'])"
assert "JSON: profile and stats keys"    "$TMP/v.json" "set(d['profile']) >= {'presentation','source'} and set(d['stats']) >= {'files','test_files','platforms','breakpoint_tokens','platform_checks','width_comparisons','layout_builders','size_reads','orientation_locks','mouse_regions','test_view_changes','skipped_generated'}"
assert "JSON: severities are known"      "$TMP/v.json" "all(f['severity'] in ('high','medium','low','info') for f in d['findings'])"
assert "JSON: package, platforms, counts" "$TMP/v.json" "d['package'] == 'adapt_violations' and d['stats']['platforms'] == ['android','ios','web','macos'] and d['stats']['platform_checks'] == 3 and d['stats']['width_comparisons'] == 2 and d['stats']['test_files'] == 1"

# --- text output
python3 -I "$CHECK" "$FIX/violations" --max 1 > "$TMP/v.txt"
head -1 "$TMP/v.txt" | grep -q '^== ADAPTIVE LAYOUT$' && pass "text: header" || bad "text: header"
sed -n 2p "$TMP/v.txt" | grep -q '^  profile: ' && pass "text: profile line" || bad "text: profile line"
sed -n 3p "$TMP/v.txt" | grep -q '^  classification: ' && pass "text: classification line" || bad "text: classification line"
sed -n 4p "$TMP/v.txt" | grep -q '^  scanned: .*platforms: android, ios, web, macos' && pass "text: scanned line" || bad "text: scanned line"
grep -Eq '^  \[ADAPT-001\] io-platform-on-web \(high\) x2 — ' "$TMP/v.txt" && pass "text: group line format" || bad "text: group line format"
grep -Eq '^      (lib|test)/[^ ]+\.dart:[0-9]+  ' "$TMP/v.txt" && pass "text: location lines" || bad "text: location lines"
grep -Eq '^      \.\.\. [0-9]+ more$' "$TMP/v.txt" && pass "text: --max collapses extra locations" || bad "text: --max collapses extra locations"
sed -n 5p "$TMP/v.txt" | grep -q '(high)' && pass "text: high groups first" || bad "text: high groups first"

# --- --files (file list and comma list)
echo "$TILE" > "$TMP/files.txt"
python3 -I "$CHECK" "$FIX/violations" --json --files "$TMP/files.txt" > "$TMP/f.json"
assert "--files: only listed files reported (breakpoints still counted project-wide)" "$TMP/f.json" "ids == {'ADAPT-004','ADAPT-008'} and all(f['file'] == '$TILE' for f in d['findings']) and '2 files' in of('ADAPT-004')[0]['note']"
python3 -I "$CHECK" "$FIX/violations" --json --files "lib/main.dart,test/catalog_view_test.dart" > "$TMP/f2.json"
assert "--files: comma list, test files included" "$TMP/f2.json" "ids == {'ADAPT-003','ADAPT-009','ADAPT-010'}"

# --- clean fixture: safe code and near-misses
python3 -I "$CHECK" "$FIX/clean" --json > "$TMP/c.json"
assert "clean: zero findings" "$TMP/c.json" "d['findings'] == [] and d['suppressed'] == []"
assert "clean: the near-misses were seen" "$TMP/c.json" "d['stats']['platform_checks'] >= 7 and d['stats']['breakpoint_tokens'] == ['WindowSizeClass'] and d['stats']['orientation_locks'] == 3 and d['stats']['mouse_regions'] == 1 and d['stats']['test_view_changes'] == 4 and 'isDesktopHost' in d['stats']['web_guards']"
python3 -I "$CHECK" "$FIX/clean" > "$TMP/c.txt"
grep -q '^  no adaptive layout findings$' "$TMP/c.txt" && pass "clean: text says no findings" || bad "clean: text says no findings"

# --- suppression
python3 -I "$CHECK" "$FIX/suppressed" --json > "$TMP/s.json"
assert "suppress: unsuppressed hit still reported" "$TMP/s.json" "[(f['id'], f['file'], f['line']) for f in d['findings']] == [('ADAPT-004', 'lib/src/line_ignored.dart', 12)]"
assert "suppress: line-above and file comments honoured" "$TMP/s.json" "sorted((s['id'], s['file'], s['line']) for s in d['suppressed']) == [('ADAPT-002','lib/src/file_ignored.dart',10), ('ADAPT-002','lib/src/file_ignored.dart',17), ('ADAPT-004','lib/src/line_ignored.dart',11)]"
assert "suppress: reasons kept" "$TMP/s.json" "all(s['reason'] and s['reason'] != '(no reason given)' for s in d['suppressed'])"
python3 -I "$CHECK" "$FIX/suppressed" | grep -q '^  suppressed: 3 (see --json)$' && pass "suppress: text summary line" || bad "suppress: text summary line"

# --- fallback without the flutter-architecture sibling
mkdir -p "$TMP/lonely/scripts"
cp "$CHECK" "$TMP/lonely/scripts/check_adaptive.py"
python3 -I "$TMP/lonely/scripts/check_adaptive.py" "$FIX/violations" --json > "$TMP/fb.json"
assert "fallback: says it used path-based classification" "$TMP/fb.json" "d['classification'].startswith('path-based fallback')"
assert "fallback: every rule still fires" "$TMP/fb.json" "ids == {'ADAPT-%03d' % i for i in range(1, 11)}"
assert "fallback: profile detected from pubspec/folders" "$TMP/fb.json" "d['profile']['presentation'] == 'mvn' and d['profile']['source'].startswith('fallback')"
python3 -I "$TMP/lonely/scripts/check_adaptive.py" "$FIX/violations" | grep -q '^  classification: path-based fallback' && pass "fallback: text output says so" || bad "fallback: text output says so"
python3 -I "$TMP/lonely/scripts/check_adaptive.py" "$FIX/clean" --json > "$TMP/fbc.json"
assert "fallback: clean fixture still zero" "$TMP/fbc.json" "d['findings'] == []"

# --- --profile override
python3 -I "$CHECK" "$FIX/violations" --json --profile bloc > "$TMP/p.json"
assert "--profile overrides detection and the placement note" "$TMP/p.json" "d['profile']['presentation'] == 'bloc' and d['profile']['source'].startswith('declared') and all('Bloc:' in f['note'] and 'MVN:' not in f['note'] for f in of('ADAPT-001') + of('ADAPT-004') + of('ADAPT-007'))"
python3 -I "$CHECK" "$FIX/violations" --json --profile getx > "$TMP/p2.json"
assert "--profile getx: the logic note names Get.width" "$TMP/p2.json" "'Get.width' in of('ADAPT-007')[0]['note']"

# --- calibration regressions (references/rules.md, Calibration)
python3 -I "$CHECK" "$FIX/calib_hiddify" --json > "$TMP/ch.json"
assert "calib_hiddify: a helper only called behind a kIsWeb-based getter is not ADAPT-001" "$TMP/ch.json" "not infile('lib/core/files/storage_paths_notifier.dart')"
assert "calib_hiddify: an unguarded check in a notifier's build() still fires (TP high)" "$TMP/ch.json" "at('lib/features/tunnel/notifier/tunnel_notifier.dart', 11, 'ADAPT-001')[0]['severity'] == 'high' and len(d['findings']) == 1"
assert "calib_hiddify: getters wrapping kIsWeb are learnt as guards" "$TMP/ch.json" "set(d['stats']['web_guards']) >= {'runsOnWindows', 'runsOnLinux'}"
python3 -I "$CHECK" "$FIX/calib_immich" --json > "$TMP/ci.json"
assert "calib_immich: platform combined with a size extension on context is not ADAPT-005" "$TMP/ci.json" "not at('lib/widgets/gallery_app_bar.dart', 10, 'ADAPT-005')"
assert "calib_immich: isTablet from the platform alone still fires (TP medium)" "$TMP/ci.json" "[(f['line'], f['severity']) for f in of('ADAPT-005')] == [(20, 'medium')]"
python3 -I "$CHECK" "$FIX/calib_lichess" --json > "$TMP/cl.json"
assert "calib_lichess: a freezed data class (with _\$X) is not a logic class" "$TMP/cl.json" "not infile('lib/src/model/settings/wallpaper.dart')"
assert "calib_lichess: a codegen notifier holding screenWidth still fires (TP medium)" "$TMP/cl.json" "at('lib/src/model/board/board_notifier.dart', 7, 'ADAPT-007')[0]['severity'] == 'medium'"
python3 -I "$CHECK" "$FIX/calib_riverpod_macos" --json > "$TMP/cr.json"
assert "calib_riverpod_macos: a macos/ folder alone is not desktop intent (no ADAPT-009)" "$TMP/cr.json" "d['findings'] == [] and d['stats']['platforms'] == ['macos']"
python3 -I "$CHECK" "$FIX/calib_samples_desktop" --json > "$TMP/cs.json"
assert "calib_samples_desktop: a desktop-first sample without a minimum size (TP low)" "$TMP/cs.json" "at('lib/main.dart', 7, 'ADAPT-009')[0]['severity'] == 'low' and 'linux, macos, windows' in at('lib/main.dart', 7, 'ADAPT-009')[0]['note']"
assert "calib_samples_desktop: Platform.isMacOS in a widget without web is low ADAPT-002" "$TMP/cs.json" "at('lib/main.dart', 18, 'ADAPT-002')[0]['severity'] == 'low' and 'ADAPT-001' not in ids"
assert "calib_samples_desktop: a test helper that never resets fires once (TP low)" "$TMP/cs.json" "[(f['file'], f['line']) for f in of('ADAPT-010')] == [('test/home_test.dart', 13)]"

# --- usage errors and edge cases
python3 -I "$CHECK" "$TMP" >/dev/null 2>&1; rc=$?
[ $rc = 2 ] && pass "exit 2 without pubspec.yaml" || bad "exit 2 without pubspec.yaml (got $rc)"
python3 -I "$CHECK" "$FIX/clean" --bogus >/dev/null 2>&1; rc=$?
[ $rc = 2 ] && pass "exit 2 on unknown option" || bad "exit 2 on unknown option (got $rc)"
python3 -I "$CHECK" "$FIX/clean" --profile nope >/dev/null 2>&1; rc=$?
[ $rc = 2 ] && pass "exit 2 on unknown profile" || bad "exit 2 on unknown profile (got $rc)"
python3 -I "$CHECK" >/dev/null 2>&1; rc=$?
[ $rc = 2 ] && pass "exit 2 without arguments" || bad "exit 2 without arguments (got $rc)"
python3 -I "$CHECK" "$FIX/clean" --max >/dev/null 2>&1; rc=$?
[ $rc = 2 ] && pass "exit 2 when an option has no value" || bad "exit 2 when an option has no value (got $rc)"
mkdir -p "$TMP/nolib"; printf 'name: nolib\n' > "$TMP/nolib/pubspec.yaml"
python3 -I "$CHECK" "$TMP/nolib" --json > "$TMP/n.json"; rc=$?
[ $rc = 0 ] && pass "no lib/: exit 0" || bad "no lib/: exit 0 (got $rc)"
assert "no lib/: empty report" "$TMP/n.json" "d['findings'] == [] and d['stats']['files'] == 0"
python3 -I "$CHECK" "$TMP/nolib" | grep -q '^  no adaptive layout findings$' && pass "no lib/: text report" || bad "no lib/: text report"

[ $fail = 0 ] && echo "ALL flutter-adaptive-layout TESTS PASSED" || echo "flutter-adaptive-layout: SOME TESTS FAILED"
exit $fail
