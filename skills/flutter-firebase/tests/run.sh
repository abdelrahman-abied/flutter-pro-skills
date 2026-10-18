#!/usr/bin/env bash
# Tests for flutter-firebase/scripts/check_firebase.py.
# No Flutter SDK, Firebase CLI or pub get needed: the checker is static. bash 3.2 compatible.
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL="$(cd "$HERE/.." && pwd)"
CHECK="$SKILL/scripts/check_firebase.py"
FIX="$HERE/fixtures"
TMP="$(mktemp -d "${TMPDIR:-/tmp}/firecheck.XXXXXX")"
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
def sev(rel, line, rid):
    hits = at(rel, line, rid)
    return hits[0]['severity'] if hits else None
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
  pass "check_firebase.py parses as Python 3.8"
else
  bad "check_firebase.py parses as Python 3.8"
fi

# --- violations fixture: every Dart and rules rule fires (FIRE-011 has its own fixture below)
before="$(checksum "$FIX/violations")"
python3 -I "$CHECK" "$FIX/violations" --json > "$TMP/v.json"; rc=$?
[ $rc = 0 ] && pass "violations: exit 0 with findings" || bad "violations: exit 0 with findings (got $rc)"
after="$(checksum "$FIX/violations")"
[ "$before" = "$after" ] && pass "read-only: fixture unchanged" || bad "read-only: fixture unchanged"
for n in 001 002 003 004 005 006 007 008 009 010 012; do
  assert "violations: FIRE-$n triggered" "$TMP/v.json" "'FIRE-$n' in ids"
done
FS=firebase/firestore.rules
SRC=lib/features/feed/data/sources/feed_remote_source.dart
NOTI=lib/features/feed/presentation/notifier/feed_notifier.dart
FLAGS=lib/features/settings/data/sources/flags_source.dart
assert "FIRE-001 high: write if true (firebase.json path) and RTDB root .read true" "$TMP/v.json" "sev('$FS', 8, 'FIRE-001') == 'high' and sev('database.rules.json', 3, 'FIRE-001') == 'high' and len(of('FIRE-001')) == 2"
assert "FIRE-001 not for a public read on one path"                "$TMP/v.json" "not at('$FS', 14, 'FIRE-001')"
assert "FIRE-002 high: test-mode timestamp and RTDB now < ms, both expired" "$TMP/v.json" "sev('$FS', 5, 'FIRE-002') == 'high' and sev('database.rules.json', 6, 'FIRE-002') == 'high' and all('expired on 2020-01-01' in f['note'] for f in of('FIRE-002'))"
assert "FIRE-003 medium on a recursive wildcard (helper resolved), low on one path" "$TMP/v.json" "sev('storage.rules', 8, 'FIRE-003') == 'medium' and sev('database.rules.json', 4, 'FIRE-003') == 'medium' and sev('$FS', 11, 'FIRE-003') == 'low'"
assert "FIRE-003 not for an owner check"                           "$TMP/v.json" "not at('$FS', 17, 'FIRE-003') and not infile('$FS') == []"
assert "FIRE-004 high: unguarded and behind a true constant"       "$TMP/v.json" "sev('lib/main.dart', 13, 'FIRE-004') == 'high' and sev('lib/main_staging.dart', 15, 'FIRE-004') == 'high' and 'hand-set constant that is true' in at('lib/main_staging.dart', 15, 'FIRE-004')[0]['note']"
assert "FIRE-004 note carries the Riverpod placement"              "$TMP/v.json" "all('Riverpod:' in f['note'] for f in of('FIRE-004'))"
assert "FIRE-005 high not awaited; medium without ensureInitialized" "$TMP/v.json" "sev('lib/main.dart', 12, 'FIRE-005') == 'high' and sev('lib/main_staging.dart', 13, 'FIRE-005') == 'medium' and len(of('FIRE-005')) == 2"
assert "FIRE-006 high: closure and handler without the pragma"     "$TMP/v.json" "sev('lib/core/messaging/push_setup.dart', 4, 'FIRE-006') == 'high' and sev('lib/main.dart', 14, 'FIRE-006') == 'high' and 'lib/main.dart:19' in at('lib/main.dart', 14, 'FIRE-006')[0]['note']"
assert "FIRE-007 low: unbounded snapshots, the limited one is quiet" "$TMP/v.json" "[(f['file'], f['line'], f['severity']) for f in of('FIRE-007')] == [('$SRC', 9, 'low')]"
assert "FIRE-008 medium: auto-dispose notifier drops its subscription" "$TMP/v.json" "sev('$NOTI', 10, 'FIRE-008') == 'medium' and 'ref.onDispose' in of('FIRE-008')[0]['note']"
assert "FIRE-009 medium: secret key and admin gate, not the welcome text" "$TMP/v.json" "[(f['line'], f['severity']) for f in of('FIRE-009')] == [(8, 'medium'), (10, 'medium')] and 'secret' in of('FIRE-009')[0]['note'] and 'security decision' in of('FIRE-009')[1]['note']"
assert "FIRE-010 medium: role written by the client"               "$TMP/v.json" "sev('$SRC', 15, 'FIRE-010') == 'medium' and '\"role\"' in of('FIRE-010')[0]['note']"
assert "FIRE-012 medium: debug provider outside kDebugMode"        "$TMP/v.json" "sev('lib/main.dart', 15, 'FIRE-012') == 'medium'"
assert "FIRE-011 quiet when App Check is activated"                "$TMP/v.json" "'FIRE-011' not in ids and d['stats']['app_check'] is True"
assert "firebase_options.dart is skipped"                          "$TMP/v.json" "not infile('lib/firebase_options.dart') and d['stats']['skipped_generated'] >= 1"
assert "uses arch_check files[] when installed"                    "$TMP/v.json" "d['classification'] == 'arch_check files[]' or d['classification'].startswith('path-based fallback (flutter-architecture')"

python3 -I "$CHECK" "$FIX/appcheck_missing" --json > "$TMP/am.json"
assert "FIRE-011 low once, at the protected dependency" "$TMP/am.json" "[(f['id'], f['file'], f['line'], f['severity']) for f in d['findings']] == [('FIRE-011', 'pubspec.yaml', 8, 'low')] and 'cloud_functions' in of('FIRE-011')[0]['note']"

# --- JSON contract (CONTRACTS §22, §36)
assert "JSON: schema and top-level keys" "$TMP/v.json" "d['schema'] == 'flutter-pro-skills/firebase@1' and set(d) >= {'schema','root','package','profile','classification','stats','findings','suppressed'}"
assert "JSON: finding keys"              "$TMP/v.json" "all(set(f) == {'id','name','severity','file','line','evidence','message','note'} for f in d['findings'])"
assert "JSON: profile and stats keys"    "$TMP/v.json" "set(d['profile']) >= {'presentation','source'} and set(d['stats']) >= {'files','firebase_packages','rules_files','index_files','emulator_calls','initialize_calls','listeners','queries','app_check','skipped_generated','sample'}"
assert "JSON: severities are known"      "$TMP/v.json" "all(f['severity'] in ('high','medium','low','info') for f in d['findings'])"
assert "JSON: package, rules and index files found via firebase.json" "$TMP/v.json" "d['package'] == 'fire_violations' and d['stats']['rules_files'] == ['firebase/firestore.rules', 'storage.rules', 'database.rules.json'] and d['stats']['index_files'] == ['firebase/firestore.indexes.json']"

# --- text output
python3 -I "$CHECK" "$FIX/violations" --max 1 > "$TMP/v.txt"
head -1 "$TMP/v.txt" | grep -q '^== FIREBASE$' && pass "text: header" || bad "text: header"
sed -n 2p "$TMP/v.txt" | grep -q '^  profile: ' && pass "text: profile line" || bad "text: profile line"
sed -n 3p "$TMP/v.txt" | grep -q '^  classification: ' && pass "text: classification line" || bad "text: classification line"
sed -n 4p "$TMP/v.txt" | grep -q '^  scanned: .*rules: firebase/firestore.rules' && pass "text: scanned line" || bad "text: scanned line"
grep -Eq '^  \[FIRE-001\] rules-open-access \(high\) x2 — ' "$TMP/v.txt" && pass "text: group line format" || bad "text: group line format"
grep -Eq '^      (lib/[^ ]+\.dart|[^ ]+\.rules|database\.rules\.json):[0-9]+  ' "$TMP/v.txt" && pass "text: location lines" || bad "text: location lines"
grep -Eq '^      \.\.\. [0-9]+ more$' "$TMP/v.txt" && pass "text: --max collapses extra locations" || bad "text: --max collapses extra locations"
sed -n 5p "$TMP/v.txt" | grep -q '(high)' && pass "text: high groups first" || bad "text: high groups first"

# --- --files (file list and comma list)
echo "$SRC" > "$TMP/files.txt"
python3 -I "$CHECK" "$FIX/violations" --json --files "$TMP/files.txt" > "$TMP/f.json"
assert "--files: only listed files reported" "$TMP/f.json" "ids == {'FIRE-007','FIRE-010'} and all(f['file'] == '$SRC' for f in d['findings'])"
python3 -I "$CHECK" "$FIX/violations" --json --files "storage.rules,lib/main_staging.dart" > "$TMP/f2.json"
assert "--files: comma list, rules files included" "$TMP/f2.json" "sorted({(f['id'], f['file']) for f in d['findings']}) == [('FIRE-003','storage.rules'), ('FIRE-004','lib/main_staging.dart'), ('FIRE-005','lib/main_staging.dart')]"

# --- rules at the repository root are read and reported with ../ paths
mkdir -p "$TMP/mono/.git" "$TMP/mono/app/lib"
cp "$FIX/appcheck_missing/pubspec.yaml" "$TMP/mono/app/pubspec.yaml"
cp "$FIX/appcheck_missing/lib/main.dart" "$TMP/mono/app/lib/main.dart"
printf 'service cloud.firestore {\n  match /databases/{database}/documents {\n    match /{document=**} {\n      allow read, write: if true;\n    }\n  }\n}\n' > "$TMP/mono/firestore.rules"
python3 -I "$CHECK" "$TMP/mono/app" --json > "$TMP/mono.json"
assert "monorepo: repo-root firestore.rules reported as ../firestore.rules" "$TMP/mono.json" "sev('../firestore.rules', 4, 'FIRE-001') == 'high'"
python3 -I "$CHECK" "$TMP/mono/app" --json --files "../firestore.rules" > "$TMP/mono2.json"
assert "monorepo: --files accepts the ../ path" "$TMP/mono2.json" "ids == {'FIRE-001'}"

# --- clean fixture: safe code and near-misses
python3 -I "$CHECK" "$FIX/clean" --json > "$TMP/c.json"
assert "clean: zero findings" "$TMP/c.json" "d['findings'] == [] and d['suppressed'] == []"
assert "clean: the near-misses were seen" "$TMP/c.json" "d['stats']['emulator_calls'] == 6 and d['stats']['listeners'] >= 5 and d['stats']['initialize_calls'] == 4 and d['stats']['background_handlers'] == 2 and d['stats']['writes'] >= 2 and d['stats']['remote_config_reads'] == 2 and d['stats']['rules_statements'] >= 10"
python3 -I "$CHECK" "$FIX/clean" > "$TMP/c.txt"
grep -q '^  no firebase findings$' "$TMP/c.txt" && pass "clean: text says no findings" || bad "clean: text says no findings"

# --- no Firebase dependency: nothing is reported, even with open rules and look-alike calls
python3 -I "$CHECK" "$FIX/no_firebase" --json > "$TMP/nf.json"
assert "no Firebase dependency: zero findings" "$TMP/nf.json" "d['findings'] == [] and d['stats']['firebase_packages'] == [] and d['stats']['rules_files'] == []"
python3 -I "$CHECK" "$FIX/no_firebase" | grep -q 'no Firebase dependency in pubspec.yaml, nothing to check' && pass "no Firebase dependency: text says so" || bad "no Firebase dependency: text says so"

# --- suppression
python3 -I "$CHECK" "$FIX/suppressed" --json > "$TMP/s.json"
assert "suppress: unsuppressed hit still reported" "$TMP/s.json" "[(f['id'], f['file'], f['line']) for f in d['findings']] == [('FIRE-001', 'firestore.rules', 9)]"
assert "suppress: rules, Dart line, Dart file and pubspec comments honoured" "$TMP/s.json" "sorted((s['id'], s['file'], s['line']) for s in d['suppressed']) == [('FIRE-001','firestore.rules',6), ('FIRE-004','lib/main.dart',9), ('FIRE-007','lib/src/tags_source.dart',9), ('FIRE-007','lib/src/tags_source.dart',11), ('FIRE-011','pubspec.yaml',8)]"
assert "suppress: reasons kept" "$TMP/s.json" "all(s['reason'] and s['reason'] != '(no reason given)' for s in d['suppressed'])"
python3 -I "$CHECK" "$FIX/suppressed" | grep -q '^  suppressed: 5 (see --json)$' && pass "suppress: text summary line" || bad "suppress: text summary line"

# --- fallback without the flutter-architecture sibling
mkdir -p "$TMP/lonely/scripts"
cp "$CHECK" "$TMP/lonely/scripts/check_firebase.py"
python3 -I "$TMP/lonely/scripts/check_firebase.py" "$FIX/violations" --json > "$TMP/fb.json"
assert "fallback: says it used path-based classification" "$TMP/fb.json" "d['classification'].startswith('path-based fallback')"
assert "fallback: every rule still fires" "$TMP/fb.json" "ids == {'FIRE-%03d' % i for i in range(1, 13)} - {'FIRE-011'}"
assert "fallback: profile detected from pubspec/folders" "$TMP/fb.json" "d['profile']['presentation'] == 'mvn' and d['profile']['source'].startswith('fallback')"
python3 -I "$TMP/lonely/scripts/check_firebase.py" "$FIX/violations" | grep -q '^  classification: path-based fallback' && pass "fallback: text output says so" || bad "fallback: text output says so"
python3 -I "$TMP/lonely/scripts/check_firebase.py" "$FIX/clean" --json > "$TMP/fbc.json"
assert "fallback: clean fixture still zero" "$TMP/fbc.json" "d['findings'] == []"

# --- --profile override
python3 -I "$CHECK" "$FIX/violations" --json --profile bloc > "$TMP/p.json"
assert "--profile overrides detection and the placement note" "$TMP/p.json" "d['profile']['presentation'] == 'bloc' and d['profile']['source'].startswith('declared') and all('Bloc:' in f['note'] and 'Riverpod:' not in f['note'] for f in of('FIRE-004') + of('FIRE-007') + of('FIRE-008'))"
assert "--profile bloc: the listener note names emit.forEach and close()" "$TMP/p.json" "'emit.forEach' in of('FIRE-008')[0]['note']"
python3 -I "$CHECK" "$FIX/violations" --json --profile mvn > "$TMP/p2.json"
assert "--profile mvn: the query note names the use case" "$TMP/p2.json" "'MVN:' in of('FIRE-007')[0]['note'] and 'use case' in of('FIRE-007')[0]['note']"

# --- calibration regressions (references/rules.md, Calibration)
python3 -I "$CHECK" "$FIX/calib_flutterfire/example" --json > "$TMP/cf.json"
CF=lib/main.dart
assert "calib_flutterfire: get() on the DocumentReference that add() returned is not FIRE-007" "$TMP/cf.json" "not at('$CF', 27, 'FIRE-007')"
assert "calib_flutterfire: get() on a top-level collection reference still fires (TP low)" "$TMP/cf.json" "sev('$CF', 32, 'FIRE-007') == 'low' and len(of('FIRE-007')) == 1"
assert "calib_flutterfire: emulator behind a hand-set flag in an example/ app is info" "$TMP/cf.json" "sev('$CF', 12, 'FIRE-004') == 'info' and 'sample app' in at('$CF', 12, 'FIRE-004')[0]['note']"
assert "calib_flutterfire: a kDebugMode ternary guards only its own argument" "$TMP/cf.json" "[(f['line'], f['severity']) for f in of('FIRE-012')] == [(7, 'info'), (8, 'info')]"
python3 -I "$CHECK" "$FIX/calib_io_flip" --json > "$TMP/cio.json"
assert "calib_io_flip: web-only app, initializeApp before ensureInitialized is not FIRE-005" "$TMP/cio.json" "'FIRE-005' not in ids"
assert "calib_io_flip: an emulator in main_local.dart (a dev entry point) is not FIRE-004" "$TMP/cio.json" "'FIRE-004' not in ids"
assert "calib_io_flip: {allPaths=**} parsed as a recursive match (TP medium x2)" "$TMP/cio.json" "sev('storage.rules', 6, 'FIRE-001') == 'medium' and sev('storage.rules', 5, 'FIRE-003') == 'medium'"
assert "calib_io_flip: an || inside parentheses neither crashes nor fires" "$TMP/cio.json" "not infile('firestore.rules') and d['stats']['rules_statements'] >= 4"
cp -R "$FIX/calib_io_flip" "$TMP/io_mobile"; mkdir -p "$TMP/io_mobile/android"
python3 -I "$CHECK" "$TMP/io_mobile" --json > "$TMP/ciom.json"
assert "calib_io_flip + android/: the same main() is FIRE-005 medium (TP)" "$TMP/ciom.json" "sev('lib/main_production.dart', 8, 'FIRE-005') == 'medium'"
python3 -I "$CHECK" "$FIX/calib_codelab" --json > "$TMP/cc.json"
assert "calib_codelab: test-mode rules that expired (TP high)" "$TMP/cc.json" "sev('firestore.rules', 5, 'FIRE-002') == 'high' and 'expired on 2022-08-23' in of('FIRE-002')[0]['note']"
assert "calib_codelab: an app-lifetime ChangeNotifier without dispose() is not FIRE-008" "$TMP/cc.json" "not infile('lib/app_state.dart') or 'FIRE-008' not in {f['id'] for f in infile('lib/app_state.dart')}"
assert "calib_codelab: a screen ChangeNotifier with dispose() still fires (TP medium)" "$TMP/cc.json" "sev('lib/screen_state.dart', 9, 'FIRE-008') == 'medium'"
assert "calib_codelab: initializeApp inside the state class is not FIRE-005; unbounded notes listener is FIRE-007 low" "$TMP/cc.json" "'FIRE-005' not in ids and [(f['file'], f['line']) for f in of('FIRE-007')] == [('lib/app_state.dart', 29)]"
python3 -I "$CHECK" "$FIX/calib_lichess" --json > "$TMP/cli.json"
assert "calib_lichess: a handler passed through a wrapper parameter is not FIRE-006" "$TMP/cli.json" "not infile('lib/src/binding.dart')"
assert "calib_lichess: a static handler without the pragma still fires (TP high)" "$TMP/cli.json" "[(f['file'], f['line'], f['severity']) for f in of('FIRE-006')] == [('lib/src/service/push_service.dart', 12, 'high')] and len(d['findings']) == 1"

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
mkdir -p "$TMP/nolib"; printf 'name: nolib\ndependencies:\n  firebase_core: ^3.0.0\n' > "$TMP/nolib/pubspec.yaml"
python3 -I "$CHECK" "$TMP/nolib" --json > "$TMP/n.json"; rc=$?
[ $rc = 0 ] && pass "no lib/: exit 0" || bad "no lib/: exit 0 (got $rc)"
assert "no lib/: empty report" "$TMP/n.json" "d['findings'] == [] and d['stats']['files'] == 0"
python3 -I "$CHECK" "$TMP/nolib" | grep -q '^  no firebase findings$' && pass "no lib/: text report" || bad "no lib/: text report"

[ $fail = 0 ] && echo "ALL flutter-firebase TESTS PASSED" || echo "flutter-firebase: SOME TESTS FAILED"
exit $fail
