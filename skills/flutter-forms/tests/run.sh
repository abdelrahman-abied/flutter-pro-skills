#!/usr/bin/env bash
# Tests for flutter-forms/scripts/check_forms.py.
# No Flutter SDK or pub get needed: the checker is static. bash 3.2 compatible.
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL="$(cd "$HERE/.." && pwd)"
CHECK="$SKILL/scripts/check_forms.py"
FIX="$HERE/fixtures"
TMP="$(mktemp -d "${TMPDIR:-/tmp}/formcheck.XXXXXX")"
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
  pass "check_forms.py parses as Python 3.8"
else
  bad "check_forms.py parses as Python 3.8"
fi

# --- violations fixture: every rule fires
before="$(checksum "$FIX/violations")"
python3 -I "$CHECK" "$FIX/violations" --json > "$TMP/v.json"; rc=$?
[ $rc = 0 ] && pass "violations: exit 0 with findings" || bad "violations: exit 0 with findings (got $rc)"
after="$(checksum "$FIX/violations")"
[ "$before" = "$after" ] && pass "read-only: fixture unchanged" || bad "read-only: fixture unchanged"
for n in 001 002 003 004 005 006 007 008; do
  assert "violations: FORM-$n triggered" "$TMP/v.json" "'FORM-$n' in ids"
done
A=lib/features/auth/presentation
S=lib/features/settings/presentation/view/security_view.dart
assert "FORM-001 medium for an unobscured password"      "$TMP/v.json" "at('$A/view/login_view.dart', 41, 'FORM-001')[0]['severity'] == 'medium'"
assert "FORM-001 low for an unobscured API key"          "$TMP/v.json" "at('$S', 30, 'FORM-001')[0]['severity'] == 'low'"
assert "FORM-001 through a project wrapper widget"       "$TMP/v.json" "at('$S', 29, 'FORM-001') and 'AppTextField' in d['stats']['wrappers']"
assert "FORM-003 skipped when the wrapper has no autofillHints" "$TMP/v.json" "not [f for f in of('FORM-003') if f['file'] == '$S']"
assert "FORM-002 names both missing flags"               "$TMP/v.json" "'enableSuggestions: false, autocorrect: false' in at('$A/widget/password_field.dart', 17, 'FORM-002')[0]['note']"
assert "FORM-003 password and one-time-code"             "$TMP/v.json" "sorted(f['note'].split(' ')[0] for f in of('FORM-003')) == ['otp', 'password']"
assert "FORM-004 high for a logged password"             "$TMP/v.json" "at('$A/view/login_view.dart', 26, 'FORM-004')[0]['severity'] == 'high'"
assert "FORM-004 high for an OTP sent to analytics"      "$TMP/v.json" "at('$A/widget/otp_field.dart', 16, 'FORM-004')[0]['severity'] == 'high'"
assert "FORM-004 one level lower under kDebugMode"       "$TMP/v.json" "at('$A/widget/otp_field.dart', 18, 'FORM-004')[0]['severity'] == 'medium'"
assert "FORM-005 note follows the mvn profile"           "$TMP/v.json" "of('FORM-005')[0]['note'].startswith('MVN:')"
assert "FORM-006 only for the unvalidated key"           "$TMP/v.json" "[(f['file'], f['line']) for f in of('FORM-006')] == [('$A/view/login_view.dart', 14)]"
assert "FORM-007 email (missing) and phone (text)"       "$TMP/v.json" "len(of('FORM-007')) == 2 and at('$S', 34, 'FORM-007')"
assert "FORM-008 controller and focus node"              "$TMP/v.json" "len(of('FORM-008')) == 2"
assert "uses arch_check files[] when installed"          "$TMP/v.json" "d['classification'] == 'arch_check files[]' or d['classification'].startswith('path-based fallback (flutter-architecture')"

# --- JSON contract (CONTRACTS §14)
assert "JSON: schema and top-level keys" "$TMP/v.json" "d['schema'] == 'flutter-pro-skills/forms@1' and set(d) >= {'schema','root','package','profile','stats','findings','suppressed'}"
assert "JSON: finding keys"              "$TMP/v.json" "all(set(f) == {'id','name','severity','file','line','evidence','message','note'} for f in d['findings'])"
assert "JSON: profile and stats keys"    "$TMP/v.json" "set(d['profile']) >= {'presentation','source'} and set(d['stats']) >= {'files','fields','secret_fields','otp_fields','contact_fields','forms','submit_buttons','wrappers'}"
assert "JSON: severities are known"      "$TMP/v.json" "all(f['severity'] in ('high','medium','low','info') for f in d['findings'])"
assert "JSON: package from pubspec"      "$TMP/v.json" "d['package'] == 'forms_violations'"

# --- text output (arch_check style)
python3 -I "$CHECK" "$FIX/violations" --max 1 > "$TMP/v.txt"
head -1 "$TMP/v.txt" | grep -q '^== FORMS$' && pass "text: header" || bad "text: header"
grep -Eq '^  \[FORM-001\] secret-field-not-obscured \(medium\) x[0-9]+ — ' "$TMP/v.txt" && pass "text: group line format" || bad "text: group line format"
grep -Eq '^      lib/[^ ]+\.dart:[0-9]+  ' "$TMP/v.txt" && pass "text: location lines" || bad "text: location lines"
grep -Eq '^      \.\.\. [0-9]+ more$' "$TMP/v.txt" && pass "text: --max collapses extra locations" || bad "text: --max collapses extra locations"
grep -q '^  field wrappers: AppTextField$' "$TMP/v.txt" && pass "text: lists field wrappers" || bad "text: lists field wrappers"

# --- --files (file list and comma list)
echo "lib/features/search/presentation/view/search_view.dart" > "$TMP/files.txt"
python3 -I "$CHECK" "$FIX/violations" --json --files "$TMP/files.txt" > "$TMP/f.json"
assert "--files: only listed files reported" "$TMP/f.json" "ids == {'FORM-008'} and all(f['file'].endswith('search_view.dart') for f in d['findings'])"
python3 -I "$CHECK" "$FIX/violations" --json --files "$S,lib/features/auth/presentation/widget/otp_field.dart" > "$TMP/f2.json"
assert "--files: comma list, wrappers still found across files" "$TMP/f2.json" "ids == {'FORM-001','FORM-003','FORM-004','FORM-007'} and at('$S', 29, 'FORM-001')"

# --- clean fixture: secure code and near-misses
python3 -I "$CHECK" "$FIX/clean" --json > "$TMP/c.json"
assert "clean: zero findings" "$TMP/c.json" "d['findings'] == [] and d['suppressed'] == []"
assert "clean: fields and guarded submit were seen" "$TMP/c.json" "d['stats']['fields'] >= 10 and d['stats']['secret_fields'] >= 3 and d['stats']['submit_buttons'] >= 1"
python3 -I "$CHECK" "$FIX/clean" > "$TMP/c.txt"
grep -q '^  no form findings$' "$TMP/c.txt" && pass "clean: text says no findings" || bad "clean: text says no findings"

# --- suppression
python3 -I "$CHECK" "$FIX/suppressed" --json > "$TMP/s.json"
assert "suppress: unsuppressed hit still reported" "$TMP/s.json" "[(f['id'], f['file'], f['line']) for f in d['findings']] == [('FORM-008', 'lib/src/line_ignored.dart', 19)]"
assert "suppress: line, in-call and file comments honoured" "$TMP/s.json" "sorted((s['id'], s['file']) for s in d['suppressed']) == [('FORM-001','lib/src/line_ignored.dart'), ('FORM-004','lib/src/file_ignored.dart'), ('FORM-004','lib/src/file_ignored.dart'), ('FORM-007','lib/src/line_ignored.dart')]"
assert "suppress: reasons kept" "$TMP/s.json" "all(s['reason'] and s['reason'] != '(no reason given)' for s in d['suppressed'])"
python3 -I "$CHECK" "$FIX/suppressed" | grep -q '^  suppressed: 4 (see --json)$' && pass "suppress: text summary line" || bad "suppress: text summary line"

# --- fallback without the flutter-architecture sibling
mkdir -p "$TMP/lonely/scripts"
cp "$CHECK" "$TMP/lonely/scripts/check_forms.py"
python3 -I "$TMP/lonely/scripts/check_forms.py" "$FIX/violations" --json > "$TMP/fb.json"
assert "fallback: says it used path-based classification" "$TMP/fb.json" "d['classification'].startswith('path-based fallback')"
assert "fallback: every rule still fires" "$TMP/fb.json" "ids == {'FORM-%03d' % i for i in range(1, 9)}"
assert "fallback: profile detected from pubspec/folders" "$TMP/fb.json" "d['profile']['presentation'] == 'mvn' and d['profile']['source'].startswith('fallback')"
python3 -I "$TMP/lonely/scripts/check_forms.py" "$FIX/violations" | grep -q '^  classification: path-based fallback' && pass "fallback: text output says so" || bad "fallback: text output says so"
python3 -I "$TMP/lonely/scripts/check_forms.py" "$FIX/clean" --json > "$TMP/fbc.json"
assert "fallback: clean fixture still zero" "$TMP/fbc.json" "d['findings'] == []"

# --- --profile override
python3 -I "$CHECK" "$FIX/violations" --json --profile bloc > "$TMP/p.json"
assert "--profile overrides detection and the fix hint" "$TMP/p.json" "d['profile']['presentation'] == 'bloc' and d['profile']['source'].startswith('declared') and of('FORM-005')[0]['note'].startswith('Bloc:')"

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

[ $fail = 0 ] && echo "ALL flutter-forms TESTS PASSED" || echo "flutter-forms: SOME TESTS FAILED"
exit $fail
