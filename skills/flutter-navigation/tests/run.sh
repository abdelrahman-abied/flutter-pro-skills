#!/usr/bin/env bash
# Tests for flutter-navigation/scripts/check_navigation.py.
# No Flutter SDK or pub get needed: the checker is static. bash 3.2 compatible.
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL="$(cd "$HERE/.." && pwd)"
CHECK="$SKILL/scripts/check_navigation.py"
FIX="$HERE/fixtures"
TMP="$(mktemp -d "${TMPDIR:-/tmp}/navcheck.XXXXXX")"
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
  pass "check_navigation.py parses as Python 3.8"
else
  bad "check_navigation.py parses as Python 3.8"
fi

# --- violations fixture: every rule except NAV-010 fires
before="$(checksum "$FIX/violations")"
python3 -I "$CHECK" "$FIX/violations" --json > "$TMP/v.json"; rc=$?
[ $rc = 0 ] && pass "violations: exit 0 with findings" || bad "violations: exit 0 with findings (got $rc)"
after="$(checksum "$FIX/violations")"
[ "$before" = "$after" ] && pass "read-only: fixture unchanged" || bad "read-only: fixture unchanged"
for n in 001 002 003 004 005 006 007 008 009 011 012; do
  assert "violations: NAV-$n triggered" "$TMP/v.json" "'NAV-$n' in ids"
done
R=lib/core/router
V=lib/features/auth/presentation/view/login_view.dart
assert "NAV-001 reports the unreachable second route (resolved through constants)" "$TMP/v.json" "[(f['file'], f['line']) for f in of('NAV-001')] == [('$R/routes_table.dart', 27)]"
assert "NAV-002 suggests the matching constant"            "$TMP/v.json" "at('$V', 29, 'NAV-002')[0]['note'] == 'use Routes.home'"
assert "NAV-003 int.parse of a path parameter"             "$TMP/v.json" "at('$R/routes_table.dart', 19, 'NAV-003')[0]['severity'] == 'medium'"
assert "NAV-003 forced query parameter"                    "$TMP/v.json" "len(at('$R/routes_table.dart', 32, 'NAV-003')) == 1"
assert "NAV-003 unchecked pathSegments index"              "$TMP/v.json" "len(at('lib/features/link/presentation/view/link_view.dart', 15, 'NAV-003')) == 1"
assert "NAV-003 low for an unchecked redirect target"      "$TMP/v.json" "at('$V', 16, 'NAV-003')[0]['severity'] == 'low'"
assert "NAV-004 hard cast flagged, guarded cast in a sibling route is not" "$TMP/v.json" "[(f['file'], f['line']) for f in of('NAV-004')] == [('$R/routes_table.dart', 38)]"
assert "NAV-005 launchUrl of a query parameter"            "$TMP/v.json" "[(f['file'], f['line']) for f in of('NAV-005')] == [('lib/features/link/presentation/view/link_view.dart', 11)]"
assert "NAV-006 high for a token in a pushed location"     "$TMP/v.json" "at('$V', 24, 'NAV-006')[0]['severity'] == 'high'"
assert "NAV-006 medium for PII and for a :token template"  "$TMP/v.json" "at('$V', 20, 'NAV-006')[0]['severity'] == 'medium' and at('$R/routes_table.dart', 29, 'NAV-006')[0]['severity'] == 'medium'"
assert "NAV-007 storage I/O in redirect"                   "$TMP/v.json" "[f['file'] for f in of('NAV-007')] == ['$R/app_router.dart']"
assert "NAV-008 router in build() and in a ref.watch provider" "$TMP/v.json" "sorted(f['file'] for f in of('NAV-008')) == ['$R/app_router.dart', 'lib/main.dart']"
assert "NAV-009 reported once"                             "$TMP/v.json" "len(of('NAV-009')) == 1"
assert "NAV-012 only for the router without refreshListenable" "$TMP/v.json" "[f['file'] for f in of('NAV-012')] == ['lib/main.dart']"
assert "NAV-012 note carries the profile's fix (mvn)"      "$TMP/v.json" "of('NAV-012')[0]['note'].startswith('MVN:')"
assert "uses arch_check files[] when installed"            "$TMP/v.json" "d['classification'] == 'arch_check files[]' or d['classification'].startswith('path-based fallback (flutter-architecture')"

# --- JSON contract (CONTRACTS.md §14)
assert "JSON: schema and top-level keys" "$TMP/v.json" "d['schema'] == 'flutter-pro-skills/flutter-navigation@1' and set(d) >= {'schema','root','package','profile','stats','findings','suppressed'}"
assert "JSON: finding keys"              "$TMP/v.json" "all(set(f) == {'id','name','severity','file','line','evidence','message','note'} for f in d['findings'])"
assert "JSON: profile and stats keys"    "$TMP/v.json" "set(d['profile']) >= {'presentation','source'} and set(d['stats']) >= {'files','routers','router_instances','routes','typed_routes','guards','navigation_calls'}"
assert "JSON: severities are known"      "$TMP/v.json" "all(f['severity'] in ('high','medium','low','info') for f in d['findings'])"
assert "JSON: ids follow NAV-0xx"        "$TMP/v.json" "all(__import__('re').match(r'^NAV-0\d\d$', f['id']) for f in d['findings'])"

# --- text output (arch_check style)
python3 -I "$CHECK" "$FIX/violations" --max 1 > "$TMP/v.txt"
head -1 "$TMP/v.txt" | grep -q '^== NAVIGATION$' && pass "text: header" || bad "text: header"
grep -Eq '^  \[NAV-003\] unvalidated-route-param \(medium\) x[0-9]+ — ' "$TMP/v.txt" && pass "text: group line format" || bad "text: group line format"
grep -Eq '^      lib/[^ ]+\.dart:[0-9]+  ' "$TMP/v.txt" && pass "text: location lines" || bad "text: location lines"
grep -Eq '^      \.\.\. [0-9]+ more$' "$TMP/v.txt" && pass "text: --max collapses extra locations" || bad "text: --max collapses extra locations"

# --- --files (file list and comma list)
echo "lib/features/link/presentation/view/link_view.dart" > "$TMP/files.txt"
python3 -I "$CHECK" "$FIX/violations" --json --files "$TMP/files.txt" > "$TMP/f.json"
assert "--files: only listed files reported" "$TMP/f.json" "d['findings'] and all(f['file'] == 'lib/features/link/presentation/view/link_view.dart' for f in d['findings'])"
python3 -I "$CHECK" "$FIX/violations" --json --files "lib/main.dart,lib/core/router/routes_table.dart" > "$TMP/f2.json"
assert "--files: comma list; cross-file route table still resolved" "$TMP/f2.json" "'NAV-001' in ids and 'NAV-008' in ids and all(f['file'] in ('lib/main.dart', 'lib/core/router/routes_table.dart') for f in d['findings'])"

# --- clean fixture
python3 -I "$CHECK" "$FIX/clean" --json > "$TMP/c.json"
assert "clean: zero findings" "$TMP/c.json" "d['findings'] == [] and d['suppressed'] == []"
assert "clean: routes and guard counted" "$TMP/c.json" "d['stats']['routes'] >= 6 and d['stats']['guards'] == 1 and d['stats']['router_instances'] == 1"
python3 -I "$CHECK" "$FIX/clean" > "$TMP/c.txt"
grep -q 'no navigation findings' "$TMP/c.txt" && pass "clean: text says no findings" || bad "clean: text says no findings"

# --- missing auth guard (bloc profile)
python3 -I "$CHECK" "$FIX/unguarded_bloc" --json > "$TMP/u.json"
assert "NAV-010: sign-in route without any redirect/onEnter" "$TMP/u.json" "[(f['id'], f['file']) for f in d['findings']] == [('NAV-010', 'lib/app/router.dart')]"
assert "NAV-010: fix hint follows the bloc profile" "$TMP/u.json" "d['findings'][0]['note'].startswith('Bloc:')"

# --- getx: Get.toNamed in a controller is the idiom; only the raw string is reported
python3 -I "$CHECK" "$FIX/getx" --json > "$TMP/g.json"
assert "getx: Get.toNamed(Routes.X) not flagged, raw '/home' is NAV-002 low" "$TMP/g.json" "[(f['id'], f['severity'], f['line']) for f in d['findings']] == [('NAV-002', 'low', 10)]"
assert "getx: no auth-guard rule without go_router" "$TMP/g.json" "'NAV-010' not in ids"

# --- suppression
python3 -I "$CHECK" "$FIX/suppressed" --json > "$TMP/s.json"
assert "suppress: unsuppressed hit still reported" "$TMP/s.json" "[(f['id'], f['file'], f['line']) for f in d['findings']] == [('NAV-003', 'lib/src/router.dart', 29)]"
assert "suppress: line-above, same-line and file comments honoured" "$TMP/s.json" "sorted((s['id'], s['file'], s['line']) for s in d['suppressed']) == [('NAV-003','lib/src/router.dart',19), ('NAV-003','lib/src/router.dart',25), ('NAV-004','lib/src/extras.dart',15), ('NAV-004','lib/src/extras.dart',16)]"
assert "suppress: reasons kept" "$TMP/s.json" "all(s['reason'] and s['reason'] != '(no reason given)' for s in d['suppressed'])"
python3 -I "$CHECK" "$FIX/suppressed" | grep -q '^  suppressed: 4 (see --json)$' && pass "suppress: text summary line" || bad "suppress: text summary line"

# --- fallback without the flutter-architecture sibling
mkdir -p "$TMP/lonely/scripts"
cp "$CHECK" "$TMP/lonely/scripts/check_navigation.py"
python3 -I "$TMP/lonely/scripts/check_navigation.py" "$FIX/violations" --json > "$TMP/fb.json"
assert "fallback: says it used path-based classification" "$TMP/fb.json" "d['classification'].startswith('path-based fallback')"
assert "fallback: same rules fire" "$TMP/fb.json" "ids == {'NAV-%03d' % i for i in (1, 2, 3, 4, 5, 6, 7, 8, 9, 11, 12)}"
assert "fallback: profile detected from pubspec/folders" "$TMP/fb.json" "d['profile']['presentation'] == 'mvn' and d['profile']['source'].startswith('fallback')"
python3 -I "$TMP/lonely/scripts/check_navigation.py" "$FIX/violations" | grep -q '^  classification: path-based fallback' && pass "fallback: text output says so" || bad "fallback: text output says so"
python3 -I "$TMP/lonely/scripts/check_navigation.py" "$FIX/clean" --json > "$TMP/fbc.json"
assert "fallback: clean fixture still zero" "$TMP/fbc.json" "d['findings'] == []"

# --- --profile override
python3 -I "$CHECK" "$FIX/violations" --json --profile bloc > "$TMP/p.json"
assert "--profile overrides detection and the fix hint" "$TMP/p.json" "d['profile']['presentation'] == 'bloc' and d['profile']['source'].startswith('declared') and of('NAV-012')[0]['note'].startswith('Bloc:')"

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

[ $fail = 0 ] && echo "ALL flutter-navigation TESTS PASSED" || echo "flutter-navigation: SOME TESTS FAILED"
exit $fail
