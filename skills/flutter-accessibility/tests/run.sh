#!/usr/bin/env bash
# Tests for flutter-accessibility/scripts/check_accessibility.py.
# No Flutter SDK or pub get needed: the checker is static. bash 3.2 compatible.
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL="$(cd "$HERE/.." && pwd)"
CHECK="$SKILL/scripts/check_accessibility.py"
FIX="$HERE/fixtures"
TMP="$(mktemp -d "${TMPDIR:-/tmp}/a11ycheck.XXXXXX")"
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
  pass "check_accessibility.py parses as Python 3.8"
else
  bad "check_accessibility.py parses as Python 3.8"
fi

# --- violations fixture: every rule fires
before="$(checksum "$FIX/violations")"
python3 -I "$CHECK" "$FIX/violations" --json > "$TMP/v.json"; rc=$?
[ $rc = 0 ] && pass "violations: exit 0 with findings" || bad "violations: exit 0 with findings (got $rc)"
after="$(checksum "$FIX/violations")"
[ "$before" = "$after" ] && pass "read-only: fixture unchanged" || bad "read-only: fixture unchanged"
for n in 001 002 003 004 005 006 007 008 009 010 011; do
  assert "violations: A11Y-$n triggered" "$TMP/v.json" "'A11Y-$n' in ids"
done
V=lib/features/profile/presentation/view/profile_view.dart
assert "A11Y-001 medium for a bare IconButton"            "$TMP/v.json" "at('$V', 33, 'A11Y-001')[0]['severity'] == 'medium'"
assert "A11Y-001 at a wrapper call that drops the tooltip" "$TMP/v.json" "'AppIconButton forwards tooltip' in at('$V', 34, 'A11Y-001')[0]['note'] and 'AppIconButton' in d['stats']['wrappers']"
assert "A11Y-001 not at the forwarding wrapper itself"    "$TMP/v.json" "not [f for f in of('A11Y-001') if f['file'].endswith('app_icon_button.dart')]"
assert "A11Y-002 icon-only GestureDetector"               "$TMP/v.json" "at('$V', 39, 'A11Y-002')"
assert "A11Y-003 low for an unlabelled image"             "$TMP/v.json" "at('$V', 40, 'A11Y-003')[0]['severity'] == 'low'"
assert "A11Y-004 high when app-wide (MaterialApp builder)" "$TMP/v.json" "at('lib/main.dart', 16, 'A11Y-004')[0]['severity'] == 'high'"
assert "A11Y-004 medium on one Text"                      "$TMP/v.json" "at('$V', 41, 'A11Y-004')[0]['severity'] == 'medium'"
assert "A11Y-004 low for a clamp below 200%"              "$TMP/v.json" "at('$V', 55, 'A11Y-004')[0]['severity'] == 'low'"
assert "A11Y-004 at a scale-wrapper call"                 "$TMP/v.json" "'FixedScale defaults scale' in at('$V', 56, 'A11Y-004')[0]['note']"
assert "A11Y-005 medium for a 24 dp box, low for shrinkWrap" "$TMP/v.json" "at('$V', 42, 'A11Y-005')[0]['severity'] == 'medium' and at('$V', 44, 'A11Y-005')[0]['severity'] == 'low'"
assert "A11Y-006 fixed height around Text"                "$TMP/v.json" "at('$V', 48, 'A11Y-006')"
assert "A11Y-007 high: announce, value, semanticsLabel"   "$TMP/v.json" "sorted(f['line'] for f in of('A11Y-007')) == [25, 49, 50] and all(f['severity'] == 'high' for f in of('A11Y-007'))"
assert "A11Y-007 announce note follows the mvn profile"   "$TMP/v.json" "'MVN:' in at('$V', 25, 'A11Y-007')[0]['note']"
assert "A11Y-008 computes the contrast ratio"             "$TMP/v.json" "'1.73:1' in of('A11Y-008')[0]['note'] and len(of('A11Y-008')) == 1"
assert "A11Y-009 ExcludeSemantics and excludeFromSemantics" "$TMP/v.json" "sorted(f['line'] for f in of('A11Y-009')) == [51, 52]"
assert "A11Y-010 second autofocus"                        "$TMP/v.json" "[f['line'] for f in of('A11Y-010')] == [54]"
assert "A11Y-011 announce in a notifier, MVN note"        "$TMP/v.json" "of('A11Y-011')[0]['file'].endswith('profile_notifier.dart') and of('A11Y-011')[0]['note'].split('; ')[1].startswith('MVN:')"
assert "uses arch_check files[] when installed"           "$TMP/v.json" "d['classification'] == 'arch_check files[]' or d['classification'].startswith('path-based fallback (flutter-architecture')"

# --- JSON contract (CONTRACTS §22)
assert "JSON: schema and top-level keys" "$TMP/v.json" "d['schema'] == 'flutter-pro-skills/accessibility@1' and set(d) >= {'schema','root','package','profile','classification','stats','findings','suppressed'}"
assert "JSON: finding keys"              "$TMP/v.json" "all(set(f) == {'id','name','severity','file','line','evidence','message','note'} for f in d['findings'])"
assert "JSON: profile and stats keys"    "$TMP/v.json" "set(d['profile']) >= {'presentation','source'} and set(d['stats']) >= {'files','icon_buttons','tappables','images','semantics_widgets','color_schemes','wrappers'}"
assert "JSON: severities are known"      "$TMP/v.json" "all(f['severity'] in ('high','medium','low','info') for f in d['findings'])"
assert "JSON: package from pubspec"      "$TMP/v.json" "d['package'] == 'a11y_violations'"

# --- text output
python3 -I "$CHECK" "$FIX/violations" --max 1 > "$TMP/v.txt"
head -1 "$TMP/v.txt" | grep -q '^== ACCESSIBILITY$' && pass "text: header" || bad "text: header"
sed -n 2p "$TMP/v.txt" | grep -q '^  profile: ' && pass "text: profile line" || bad "text: profile line"
sed -n 3p "$TMP/v.txt" | grep -q '^  classification: ' && pass "text: classification line" || bad "text: classification line"
sed -n 4p "$TMP/v.txt" | grep -q '^  scanned: ' && pass "text: scanned line" || bad "text: scanned line"
grep -Eq '^  \[A11Y-001\] icon-button-without-label \(medium\) x[0-9]+ — ' "$TMP/v.txt" && pass "text: group line format" || bad "text: group line format"
grep -Eq '^      lib/[^ ]+\.dart:[0-9]+  ' "$TMP/v.txt" && pass "text: location lines" || bad "text: location lines"
grep -Eq '^      \.\.\. [0-9]+ more$' "$TMP/v.txt" && pass "text: --max collapses extra locations" || bad "text: --max collapses extra locations"

# --- --files (file list and comma list)
echo "lib/core/theme/app_colors.dart" > "$TMP/files.txt"
python3 -I "$CHECK" "$FIX/violations" --json --files "$TMP/files.txt" > "$TMP/f.json"
assert "--files: only listed files reported" "$TMP/f.json" "ids == {'A11Y-008'} and all(f['file'].endswith('app_colors.dart') for f in d['findings'])"
python3 -I "$CHECK" "$FIX/violations" --json --files "lib/main.dart,lib/features/profile/presentation/notifier/profile_notifier.dart" > "$TMP/f2.json"
assert "--files: comma list" "$TMP/f2.json" "ids == {'A11Y-004','A11Y-011'}"

# --- clean fixture: accessible code and near-misses
python3 -I "$CHECK" "$FIX/clean" --json > "$TMP/c.json"
assert "clean: zero findings" "$TMP/c.json" "d['findings'] == [] and d['suppressed'] == []"
assert "clean: widgets were seen" "$TMP/c.json" "d['stats']['icon_buttons'] >= 6 and d['stats']['images'] >= 3 and d['stats']['semantics_widgets'] >= 8 and d['stats']['color_schemes'] >= 1"
python3 -I "$CHECK" "$FIX/clean" > "$TMP/c.txt"
grep -q '^  no accessibility findings$' "$TMP/c.txt" && pass "clean: text says no findings" || bad "clean: text says no findings"

# --- suppression
python3 -I "$CHECK" "$FIX/suppressed" --json > "$TMP/s.json"
assert "suppress: unsuppressed hits still reported" "$TMP/s.json" "sorted((f['id'], f['line']) for f in d['findings']) == [('A11Y-001', 17), ('A11Y-003', 16)]"
assert "suppress: line, in-call and file comments honoured" "$TMP/s.json" "sorted((s['id'], s['file'], s['line']) for s in d['suppressed']) == [('A11Y-001','lib/src/line_ignored.dart',11), ('A11Y-001','lib/src/line_ignored.dart',12), ('A11Y-004','lib/src/file_ignored.dart',11), ('A11Y-004','lib/src/file_ignored.dart',12)]"
assert "suppress: reasons kept" "$TMP/s.json" "all(s['reason'] and s['reason'] != '(no reason given)' for s in d['suppressed'])"
python3 -I "$CHECK" "$FIX/suppressed" | grep -q '^  suppressed: 4 (see --json)$' && pass "suppress: text summary line" || bad "suppress: text summary line"

# --- calibration regressions (references/rules.md, Calibration)
python3 -I "$CHECK" "$FIX/calib_riverpod_marvel" --json > "$TMP/k1.json"
assert "calib marvel: conditional ExcludeSemantics(excluding: expr) not flagged" "$TMP/k1.json" "not at('lib/src/widgets/search_bar.dart', 13, 'A11Y-009')"
assert "calib marvel: always-excluded TextField still flagged" "$TMP/k1.json" "[(f['id'], f['line']) for f in d['findings']] == [('A11Y-009', 18)]"
python3 -I "$CHECK" "$FIX/calib_immich" --json > "$TMP/k2.json"
assert "calib immich: autofocus in ternary branches not flagged" "$TMP/k2.json" "not [f for f in of('A11Y-010') if f['line'] < 20]"
assert "calib immich: two built autofocus fields still flagged" "$TMP/k2.json" "[(f['id'], f['line']) for f in d['findings']] == [('A11Y-010', 28)]"
python3 -I "$CHECK" "$FIX/calib_bloc_todos" --json > "$TMP/k3.json"
assert "calib todos: forwarded icon labelled at every call site not flagged" "$TMP/k3.json" "not at('lib/home/view/home_page.dart', 26, 'A11Y-001')"
assert "calib todos: forwarded unlabelled icon still flagged" "$TMP/k3.json" "[(f['id'], f['line']) for f in d['findings']] == [('A11Y-001', 38)]"

# --- fallback without the flutter-architecture sibling
mkdir -p "$TMP/lonely/scripts"
cp "$CHECK" "$TMP/lonely/scripts/check_accessibility.py"
python3 -I "$TMP/lonely/scripts/check_accessibility.py" "$FIX/violations" --json > "$TMP/fb.json"
assert "fallback: says it used path-based classification" "$TMP/fb.json" "d['classification'].startswith('path-based fallback')"
assert "fallback: every rule still fires" "$TMP/fb.json" "ids == {'A11Y-%03d' % i for i in range(1, 12)}"
assert "fallback: profile detected from pubspec/folders" "$TMP/fb.json" "d['profile']['presentation'] == 'mvn' and d['profile']['source'].startswith('fallback')"
python3 -I "$TMP/lonely/scripts/check_accessibility.py" "$FIX/violations" | grep -q '^  classification: path-based fallback' && pass "fallback: text output says so" || bad "fallback: text output says so"
python3 -I "$TMP/lonely/scripts/check_accessibility.py" "$FIX/clean" --json > "$TMP/fbc.json"
assert "fallback: clean fixture still zero" "$TMP/fbc.json" "d['findings'] == []"

# --- --profile override
python3 -I "$CHECK" "$FIX/violations" --json --profile bloc > "$TMP/p.json"
assert "--profile overrides detection and the fix hint" "$TMP/p.json" "d['profile']['presentation'] == 'bloc' and d['profile']['source'].startswith('declared') and 'Bloc:' in of('A11Y-011')[0]['note'] and 'Bloc:' in at('$V', 25, 'A11Y-007')[0]['note']"

# --- usage errors and edge cases
python3 -I "$CHECK" "$TMP" >/dev/null 2>&1; rc=$?
[ $rc = 2 ] && pass "exit 2 without pubspec.yaml" || bad "exit 2 without pubspec.yaml (got $rc)"
python3 -I "$CHECK" "$FIX/clean" --bogus >/dev/null 2>&1; rc=$?
[ $rc = 2 ] && pass "exit 2 on unknown option" || bad "exit 2 on unknown option (got $rc)"
python3 -I "$CHECK" "$FIX/clean" --profile nope >/dev/null 2>&1; rc=$?
[ $rc = 2 ] && pass "exit 2 on unknown profile" || bad "exit 2 on unknown profile (got $rc)"
python3 -I "$CHECK" >/dev/null 2>&1; rc=$?
[ $rc = 2 ] && pass "exit 2 without arguments" || bad "exit 2 without arguments (got $rc)"
mkdir -p "$TMP/nolib"; printf 'name: nolib\n' > "$TMP/nolib/pubspec.yaml"
python3 -I "$CHECK" "$TMP/nolib" --json > "$TMP/n.json"; rc=$?
[ $rc = 0 ] && pass "no lib/: exit 0" || bad "no lib/: exit 0 (got $rc)"
assert "no lib/: empty report" "$TMP/n.json" "d['findings'] == [] and d['stats']['files'] == 0"

[ $fail = 0 ] && echo "ALL flutter-accessibility TESTS PASSED" || echo "flutter-accessibility: SOME TESTS FAILED"
exit $fail
