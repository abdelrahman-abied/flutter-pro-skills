#!/usr/bin/env bash
# Tests for flutter-i18n/scripts/check_i18n.py.
# No Flutter SDK or pub get needed: the checker is static. bash 3.2 compatible.
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL="$(cd "$HERE/.." && pwd)"
CHECK="$SKILL/scripts/check_i18n.py"
FIX="$HERE/fixtures"
TMP="$(mktemp -d "${TMPDIR:-/tmp}/i18ncheck.XXXXXX")"
trap 'rm -rf "$TMP"' EXIT
fail=0

pass() { echo "PASS $1"; }
bad() { echo "FAIL $1"; fail=1; }

# assert <name> <json-file> <python-expression over d (the report) and ids (set of rule ids)>
assert() {
  local name="$1" file="$2" expr="$3"
  if python3 -I - "$file" "$expr" <<'PY'
import json, sys
d = json.load(open(sys.argv[1], encoding='utf-8'))
ids = {f['id'] for f in d['findings']}
def at(rel, line, rid):
    return [f for f in d['findings'] if f['file'] == rel and f['line'] == line and f['id'] == rid]
def sev(rel, line, rid):
    return [f['severity'] for f in at(rel, line, rid)]
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
  pass "check_i18n.py parses as Python 3.8"
else
  bad "check_i18n.py parses as Python 3.8"
fi

# --- violations fixture (gen-l10n, en + ar, MVN): every rule fires
V=lib/features/cart/presentation/view/cart_view.dart
before="$(checksum "$FIX/violations")"
python3 -I "$CHECK" "$FIX/violations" --json > "$TMP/v.json"; rc=$?
[ $rc = 0 ] && pass "violations: exit 0 with findings" || bad "violations: exit 0 with findings (got $rc)"
after="$(checksum "$FIX/violations")"
[ "$before" = "$after" ] && pass "read-only: fixture unchanged" || bad "read-only: fixture unchanged"
for n in 001 002 003 004 005 006 010 011 012 013 014 015 016 017 018; do
  assert "violations: I18N-$n triggered" "$TMP/v.json" "'I18N-$n' in ids"
done
assert "I18N-001 names the missing ar key"              "$TMP/v.json" "'checkout' in at('lib/l10n/app_ar.arb', 1, 'I18N-001')[0]['evidence']"
assert "I18N-002 flags a translated placeholder name"   "$TMP/v.json" "'not a Dart identifier' in at('lib/l10n/app_ar.arb', 5, 'I18N-002')[0]['note']"
assert "I18N-003 Arabic plural lacks few and many"      "$TMP/v.json" "'missing few, many' in at('lib/l10n/app_ar.arb', 6, 'I18N-003')[0]['evidence']"
assert "I18N-004 masks the secret in evidence"          "$TMP/v.json" "all('AIzaSyD4x9' not in f['evidence'] for f in d['findings'] if f['id'] == 'I18N-004')"
assert "I18N-005 high for synthetic-package: true"      "$TMP/v.json" "sev('l10n.yaml', 4, 'I18N-005') == ['high'] and sev('lib/main.dart', 2, 'I18N-005') == ['medium']"
assert "I18N-016 high when an RTL locale ships"         "$TMP/v.json" "sev('lib/main.dart', 14, 'I18N-016') == ['high']"
assert "I18N-010 low for prose, info for one word"      "$TMP/v.json" "sev('$V', 22, 'I18N-010') == ['low'] and sev('$V', 23, 'I18N-010') == ['info'] and sev('$V', 24, 'I18N-010') == ['low']"
assert "I18N-011 medium for words, low for punctuation" "$TMP/v.json" "sev('$V', 29, 'I18N-011') == ['medium'] and sev('$V', 27, 'I18N-011') == ['low']"
assert "I18N-011 literal is not also I18N-010"          "$TMP/v.json" "at('$V', 29, 'I18N-010') == [] and at('$V', 27, 'I18N-010') == []"
assert "I18N-018 mojibake literal is not also I18N-010" "$TMP/v.json" "at('$V', 33, 'I18N-010') == [] and at('$V', 33, 'I18N-018')"
assert "I18N-015 note carries the detected profile's fix" "$TMP/v.json" "at('lib/features/cart/presentation/notifier/cart_notifier.dart', 14, 'I18N-015')[0]['note'].split(':')[0].lower() == d['profile']['presentation']"
python3 -I "$CHECK" "$FIX/violations" --json --profile mvn > "$TMP/vm.json"
assert "I18N-015 note carries the MVN fix under --profile mvn" "$TMP/vm.json" "at('lib/features/cart/presentation/notifier/cart_notifier.dart', 14, 'I18N-015')[0]['note'].startswith('MVN:')"
assert "negatives: keys, values, debug, assets, symmetric padding, direction-aware icons" "$TMP/v.json" \
  "not [f for f in d['findings'] if f['file'] == '$V' and f['line'] >= 34]"
assert "uses arch_check files[] when installed"         "$TMP/v.json" "d['classification'] == 'arch_check files[]' or d['classification'].startswith('path-based fallback (flutter-architecture')"

# --- JSON contract (CONTRACTS §14)
assert "JSON: schema and top-level keys" "$TMP/v.json" "d['schema'] == 'flutter-pro-skills/i18n@1' and set(d) >= {'schema','root','package','profile','stats','findings','suppressed'}"
assert "JSON: finding keys"              "$TMP/v.json" "all(set(f) == {'id','name','severity','file','line','evidence','message','note'} for f in d['findings'])"
assert "JSON: stats keys"                "$TMP/v.json" "set(d['stats']) >= {'files','catalog_files','catalogs','systems','localised','locales','rtl_locales'} and d['stats']['rtl_locales'] == ['ar']"
assert "JSON: severities are known"      "$TMP/v.json" "all(f['severity'] in ('high','medium','low','info') for f in d['findings'])"
assert "JSON: ids are I18N-0xx"          "$TMP/v.json" "all(f['id'].startswith('I18N-0') and len(f['id']) == 8 for f in d['findings'])"

# --- text output
python3 -I "$CHECK" "$FIX/violations" --max 1 > "$TMP/v.txt"
head -1 "$TMP/v.txt" | grep -q '^== I18N$' && pass "text: header" || bad "text: header"
grep -Eq '^  \[I18N-010\] hardcoded-ui-string \(low\) x[0-9]+ — ' "$TMP/v.txt" && pass "text: group line format" || bad "text: group line format"
grep -Eq '^      lib/[^ ]+\.(dart|arb):[0-9]+  ' "$TMP/v.txt" && pass "text: location lines" || bad "text: location lines"
grep -Eq '^      \.\.\. [0-9]+ more$' "$TMP/v.txt" && pass "text: --max collapses extra locations" || bad "text: --max collapses extra locations"
grep -q '^  localisation: gen-l10n (lib/l10n, template app_en.arb), 2 locales; RTL: ar$' "$TMP/v.txt" && pass "text: localisation line" || bad "text: localisation line"

# --- --files (file list and comma list)
echo "$V" > "$TMP/files.txt"
python3 -I "$CHECK" "$FIX/violations" --json --files "$TMP/files.txt" > "$TMP/f.json"
assert "--files: only listed files reported" "$TMP/f.json" "d['findings'] and all(f['file'] == '$V' for f in d['findings'])"
python3 -I "$CHECK" "$FIX/violations" --json --files "lib/l10n/app_ar.arb,lib/main.dart" > "$TMP/f2.json"
assert "--files: comma list, catalog parity still uses the template" "$TMP/f2.json" "ids >= {'I18N-001','I18N-002','I18N-003','I18N-016'} and all(f['file'] in ('lib/l10n/app_ar.arb','lib/main.dart') for f in d['findings'])"

# --- clean fixture: zero findings
python3 -I "$CHECK" "$FIX/clean" --json > "$TMP/c.json"
assert "clean: zero findings" "$TMP/c.json" "d['findings'] == [] and d['suppressed'] == []"
assert "clean: still sees the ar catalog and RTL" "$TMP/c.json" "d['stats']['rtl_locales'] == ['ar'] and d['stats']['catalog_files'] == 2"
python3 -I "$CHECK" "$FIX/clean" > "$TMP/c.txt"
grep -q '^  no i18n findings$' "$TMP/c.txt" && pass "clean: text says no findings" || bad "clean: text says no findings"

# --- suppression (Dart line, Dart file, ARB @@x-i18n-ignore)
python3 -I "$CHECK" "$FIX/suppressed" --json > "$TMP/s.json"
assert "suppress: unsuppressed hit still reported" "$TMP/s.json" "[(f['id'], f['file'], f['line']) for f in d['findings']] == [('I18N-010', 'lib/ui/line_ignored.dart', 13)]"
assert "suppress: line-above, same-line, file and ARB honoured" "$TMP/s.json" "sorted((s['id'], s['file'], s['line']) for s in d['suppressed']) == [('I18N-001','lib/l10n/app_ar.arb',1), ('I18N-010','lib/ui/line_ignored.dart',11), ('I18N-010','lib/ui/line_ignored.dart',12), ('I18N-012','lib/ui/file_ignored.dart',11), ('I18N-012','lib/ui/file_ignored.dart',12)]"
assert "suppress: reasons kept" "$TMP/s.json" "all(s['reason'] and s['reason'] != '(no reason given)' for s in d['suppressed'])"
python3 -I "$CHECK" "$FIX/suppressed" | grep -q '^  suppressed: 5 (see --json)$' && pass "suppress: text summary line" || bad "suppress: text summary line"

# --- easy_localization JSON catalogs
python3 -I "$CHECK" "$FIX/easy" --json > "$TMP/e.json"
assert "easy_localization: system detected" "$TMP/e.json" "d['stats']['systems'] == ['easy_localization'] and d['stats']['rtl_locales'] == ['ar']"
assert "easy_localization: parity, placeholders, Arabic plurals" "$TMP/e.json" "at('assets/translations/ar.json', 1, 'I18N-001') and 'drops {name}' in at('assets/translations/ar.json', 4, 'I18N-002')[0]['evidence'] and at('assets/translations/ar.json', 6, 'I18N-003')"
assert "easy_localization: .tr() keys are not hardcoded strings" "$TMP/e.json" "sorted((f['id'], f['line']) for f in d['findings'] if f['file'].startswith('lib/')) == [('I18N-010', 14), ('I18N-011', 13)]"

# --- GetX: .tr respected, controller .tr graded low
python3 -I "$CHECK" "$FIX/getx" --json > "$TMP/g.json"
C=lib/app/modules/home/controllers/home_controller.dart
assert "getx: profile and Translations detected" "$TMP/g.json" "d['profile']['presentation'] == 'getx' and 'getx' in d['stats']['systems'] and d['stats']['rtl_locales'] == ['ar']"
assert "getx: 'key'.tr in a view is not reported" "$TMP/g.json" "not [f for f in d['findings'] if f['id'] in ('I18N-010','I18N-011') and 'views/' in f['file']]"
assert "getx: .tr in a controller is low, Get.snackbar literals reported" "$TMP/g.json" "sev('$C', 7, 'I18N-015') == ['low'] and sorted(sev('$C', 8, 'I18N-010')) == ['info', 'low']"
assert "getx: GetMaterialApp without delegates is high (ships ar)" "$TMP/g.json" "sev('lib/main.dart', 7, 'I18N-016') == ['high']"

# --- not localised: no catalog rules, no hardcoded-string or RTL noise
python3 -I "$CHECK" "$FIX/plain" --json > "$TMP/p.json"
assert "plain: unlocalised app reports nothing" "$TMP/p.json" "d['findings'] == [] and d['stats']['localised'] is False"

# --- fallback without the flutter-architecture sibling
mkdir -p "$TMP/lonely/scripts"
cp "$CHECK" "$TMP/lonely/scripts/check_i18n.py"
python3 -I "$TMP/lonely/scripts/check_i18n.py" "$FIX/violations" --json > "$TMP/fb.json"
assert "fallback: says it used path-based classification" "$TMP/fb.json" "d['classification'].startswith('path-based fallback')"
assert "fallback: every rule still fires" "$TMP/fb.json" "ids == {'I18N-0%02d' % i for i in (1, 2, 3, 4, 5, 6, 10, 11, 12, 13, 14, 15, 16, 17, 18)}"
assert "fallback: profile detected from pubspec/folders" "$TMP/fb.json" "d['profile']['presentation'] == 'mvn' and d['profile']['source'].startswith('fallback')"
python3 -I "$TMP/lonely/scripts/check_i18n.py" "$FIX/violations" | grep -q '^  classification: path-based fallback' && pass "fallback: text output says so" || bad "fallback: text output says so"
python3 -I "$TMP/lonely/scripts/check_i18n.py" "$FIX/clean" --json > "$TMP/fbc.json"
assert "fallback: clean fixture still zero" "$TMP/fbc.json" "d['findings'] == []"

# --- --profile override
python3 -I "$CHECK" "$FIX/violations" --json --profile bloc > "$TMP/pr.json"
assert "--profile overrides detection and the fix hint" "$TMP/pr.json" "d['profile']['presentation'] == 'bloc' and d['profile']['source'].startswith('declared') and [f['note'] for f in d['findings'] if f['id'] == 'I18N-015'][0].startswith('Bloc:')"

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
mkdir -p "$TMP/badarb/lib/l10n"; printf 'name: badarb\n' > "$TMP/badarb/pubspec.yaml"
printf '{"a": "A", "b": "B"}' > "$TMP/badarb/lib/l10n/app_en.arb"; printf '{"a": "A",, }' > "$TMP/badarb/lib/l10n/app_ar.arb"
python3 -I "$CHECK" "$TMP/badarb" --json > "$TMP/ba.json"; rc=$?
[ $rc = 0 ] && pass "malformed ARB: exit 0" || bad "malformed ARB: exit 0 (got $rc)"
assert "malformed ARB: listed as unreadable, not as missing keys" "$TMP/ba.json" "d['stats']['catalogs'][0]['unreadable'] == ['lib/l10n/app_ar.arb'] and d['findings'] == []"

[ $fail = 0 ] && echo "ALL flutter-i18n TESTS PASSED" || echo "flutter-i18n: SOME TESTS FAILED"
exit $fail
