#!/usr/bin/env bash
# Tests for flutter-persistence/scripts/check_persistence.py.
# No Flutter SDK or pub get needed: the checker is static. bash 3.2 compatible.
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL="$(cd "$HERE/.." && pwd)"
CHECK="$SKILL/scripts/check_persistence.py"
FIX="$HERE/fixtures"
TMP="$(mktemp -d "${TMPDIR:-/tmp}/persistcheck.XXXXXX")"
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
  pass "check_persistence.py parses as Python 3.8"
else
  bad "check_persistence.py parses as Python 3.8"
fi

# --- violations fixture: every rule fires
before="$(checksum "$FIX/violations")"
python3 -I "$CHECK" "$FIX/violations" --json > "$TMP/v.json"; rc=$?
[ $rc = 0 ] && pass "violations: exit 0 with findings" || bad "violations: exit 0 with findings (got $rc)"
after="$(checksum "$FIX/violations")"
[ "$before" = "$after" ] && pass "read-only: fixture unchanged" || bad "read-only: fixture unchanged"
for n in 001 002 003 004 005 006 007 008 009; do
  assert "violations: PERSIST-$n triggered" "$TMP/v.json" "'PERSIST-$n' in ids"
done
SRC=lib/features/notes/data/sources/notes_local_source.dart
REPO=lib/features/notes/data/repositories/notes_repository_impl.dart
DB=lib/core/database
assert "PERSIST-001 high: string parameter interpolated into LIKE"   "$TMP/v.json" "at('$SRC', 14, 'PERSIST-001')[0]['severity'] == 'high' and 'parameter of search' in at('$SRC', 14, 'PERSIST-001')[0]['note']"
assert "PERSIST-001 high: concatenation, unquoted value position"   "$TMP/v.json" "at('$SRC', 18, 'PERSIST-001')[0]['severity'] == 'high' and 'bind it' in at('$SRC', 18, 'PERSIST-001')[0]['note']"
assert "PERSIST-001 high: sqflite where: string"                    "$TMP/v.json" "at('$SRC', 26, 'PERSIST-001')[0]['severity'] == 'high'"
assert "PERSIST-001 low: untraceable field as identifier"            "$TMP/v.json" "at('$SRC', 22, 'PERSIST-001')[0]['severity'] == 'low' and 'allow-list' in at('$SRC', 22, 'PERSIST-001')[0]['note']"
assert "PERSIST-001 constant table name alone is not reported"      "$TMP/v.json" "len([f for f in of('PERSIST-001') if f['file'] == '$SRC']) == 4"
assert "PERSIST-001 skips PRAGMA with a migration version"           "$TMP/v.json" "not infile('$DB/history_database.dart') or [f['id'] for f in infile('$DB/history_database.dart')] == ['PERSIST-008']"
assert "PERSIST-002 no migration getter"                             "$TMP/v.json" "'no migration getter' in at('$DB/app_database.dart', 20, 'PERSIST-002')[0]['note']"
assert "PERSIST-002 MigrationStrategy without onUpgrade (const version)" "$TMP/v.json" "'has no onUpgrade' in at('$DB/cache_database.dart', 12, 'PERSIST-002')[0]['note'] and 'schemaVersion 2' in at('$DB/cache_database.dart', 12, 'PERSIST-002')[0]['note']"
assert "PERSIST-003 resolves a const version"                        "$TMP/v.json" "'version: 3' in at('$DB/legacy_sqflite.dart', 6, 'PERSIST-003')[0]['note']"
assert "PERSIST-004 names the first owner of the id"                 "$TMP/v.json" "'NoteModel' in at('lib/features/notes/data/models/note_model.dart', 21, 'PERSIST-004')[0]['note']"
assert "PERSIST-005 duplicate index inside one class"                "$TMP/v.json" "len(of('PERSIST-005')) == 1 and of('PERSIST-005')[0]['line'] == 15"
assert "PERSIST-006 auto-disposed @riverpod provider"                "$TMP/v.json" "'auto-disposed @riverpod' in at('lib/core/di/database_providers.dart', 10, 'PERSIST-006')[0]['note']"
assert "PERSIST-006 get_it registerFactory"                          "$TMP/v.json" "'registerFactory' in at('lib/core/di/database_providers.dart', 16, 'PERSIST-006')[0]['note']"
assert "PERSIST-006 per call in a repository method"                 "$TMP/v.json" "'loadNotes()' in at('$REPO', 14, 'PERSIST-006')[0]['note']"
assert "PERSIST-007 drift and sqflite loops"                         "$TMP/v.json" "at('$REPO', 23, 'PERSIST-007') and at('$SRC', 31, 'PERSIST-007')"
assert "PERSIST-008 only for the database with a migration"          "$TMP/v.json" "[(f['file'], f['line']) for f in of('PERSIST-008')] == [('$DB/history_database.dart', 10)]"
assert "PERSIST-009 medium for medical, low for payments"            "$TMP/v.json" "sorted(f['severity'] for f in of('PERSIST-009')) == ['low', 'medium', 'medium']"
assert "notes carry the MVN placement"                               "$TMP/v.json" "all('MVN:' in f['note'] for f in of('PERSIST-001') + of('PERSIST-006') + of('PERSIST-007'))"
assert "uses arch_check files[] when installed"                      "$TMP/v.json" "d['classification'] == 'arch_check files[]' or d['classification'].startswith('path-based fallback (flutter-architecture')"

# --- JSON contract (CONTRACTS §22)
assert "JSON: schema and top-level keys" "$TMP/v.json" "d['schema'] == 'flutter-pro-skills/persistence@1' and set(d) >= {'schema','root','package','profile','classification','stats','findings','suppressed'}"
assert "JSON: finding keys"              "$TMP/v.json" "all(set(f) == {'id','name','severity','file','line','evidence','message','note'} for f in d['findings'])"
assert "JSON: profile and stats keys"    "$TMP/v.json" "set(d['profile']) >= {'presentation','source'} and set(d['stats']) >= {'files','stores','sql_calls','drift_databases','sqflite_opens','hive_types'}"
assert "JSON: severities are known"      "$TMP/v.json" "all(f['severity'] in ('high','medium','low','info') for f in d['findings'])"
assert "JSON: package and stores"        "$TMP/v.json" "d['package'] == 'persist_violations' and d['stats']['stores'] == ['drift', 'hive', 'sqflite']"

# --- text output (arch_check style)
python3 -I "$CHECK" "$FIX/violations" --max 1 > "$TMP/v.txt"
head -1 "$TMP/v.txt" | grep -q '^== PERSISTENCE$' && pass "text: header" || bad "text: header"
sed -n 2p "$TMP/v.txt" | grep -q '^  profile: ' && pass "text: profile line" || bad "text: profile line"
sed -n 3p "$TMP/v.txt" | grep -q '^  classification: ' && pass "text: classification line" || bad "text: classification line"
sed -n 4p "$TMP/v.txt" | grep -q '^  scanned: ' && pass "text: scanned line" || bad "text: scanned line"
grep -Eq '^  \[PERSIST-001\] sql-built-from-strings \(high\) x3 — ' "$TMP/v.txt" && pass "text: group line format" || bad "text: group line format"
grep -Eq '^      lib/[^ ]+\.dart:[0-9]+  ' "$TMP/v.txt" && pass "text: location lines" || bad "text: location lines"
grep -Eq '^      \.\.\. [0-9]+ more$' "$TMP/v.txt" && pass "text: --max collapses extra locations" || bad "text: --max collapses extra locations"

# --- --files (file list and comma list)
echo "$SRC" > "$TMP/files.txt"
python3 -I "$CHECK" "$FIX/violations" --json --files "$TMP/files.txt" > "$TMP/f.json"
assert "--files: only listed files reported" "$TMP/f.json" "ids == {'PERSIST-001','PERSIST-007'} and all(f['file'] == '$SRC' for f in d['findings'])"
python3 -I "$CHECK" "$FIX/violations" --json --files "lib/features/notes/data/models/note_model.dart,$DB/legacy_sqflite.dart" > "$TMP/f2.json"
assert "--files: comma list, type ids still resolved across the project" "$TMP/f2.json" "ids == {'PERSIST-003','PERSIST-004','PERSIST-005'}"

# --- clean fixture: safe code and near-misses
python3 -I "$CHECK" "$FIX/clean" --json > "$TMP/c.json"
assert "clean: zero findings" "$TMP/c.json" "d['findings'] == [] and d['suppressed'] == []"
assert "clean: storage code was seen" "$TMP/c.json" "d['stats']['sql_calls'] >= 8 and d['stats']['drift_databases'] == 1 and d['stats']['sqflite_opens'] == 3 and d['stats']['hive_types'] == 2"
python3 -I "$CHECK" "$FIX/clean" > "$TMP/c.txt"
grep -q '^  no persistence findings$' "$TMP/c.txt" && pass "clean: text says no findings" || bad "clean: text says no findings"

# --- suppression
python3 -I "$CHECK" "$FIX/suppressed" --json > "$TMP/s.json"
assert "suppress: unsuppressed hit still reported" "$TMP/s.json" "[(f['id'], f['file'], f['line']) for f in d['findings']] == [('PERSIST-001', 'lib/src/line_ignored.dart', 14)]"
assert "suppress: line-above and file comments honoured" "$TMP/s.json" "sorted((s['id'], s['file']) for s in d['suppressed']) == [('PERSIST-001','lib/src/line_ignored.dart'), ('PERSIST-007','lib/src/file_ignored.dart'), ('PERSIST-007','lib/src/file_ignored.dart')]"
assert "suppress: reasons kept" "$TMP/s.json" "all(s['reason'] and s['reason'] != '(no reason given)' for s in d['suppressed'])"
python3 -I "$CHECK" "$FIX/suppressed" | grep -q '^  suppressed: 3 (see --json)$' && pass "suppress: text summary line" || bad "suppress: text summary line"

# --- fallback without the flutter-architecture sibling
mkdir -p "$TMP/lonely/scripts"
cp "$CHECK" "$TMP/lonely/scripts/check_persistence.py"
python3 -I "$TMP/lonely/scripts/check_persistence.py" "$FIX/violations" --json > "$TMP/fb.json"
assert "fallback: says it used path-based classification" "$TMP/fb.json" "d['classification'].startswith('path-based fallback')"
assert "fallback: every rule still fires" "$TMP/fb.json" "ids == {'PERSIST-%03d' % i for i in range(1, 10)}"
assert "fallback: profile detected from pubspec/folders" "$TMP/fb.json" "d['profile']['presentation'] == 'mvn' and d['profile']['source'].startswith('fallback')"
python3 -I "$TMP/lonely/scripts/check_persistence.py" "$FIX/violations" | grep -q '^  classification: path-based fallback' && pass "fallback: text output says so" || bad "fallback: text output says so"
python3 -I "$TMP/lonely/scripts/check_persistence.py" "$FIX/clean" --json > "$TMP/fbc.json"
assert "fallback: clean fixture still zero" "$TMP/fbc.json" "d['findings'] == []"

# --- --profile override
python3 -I "$CHECK" "$FIX/violations" --json --profile bloc > "$TMP/p.json"
assert "--profile overrides detection and the placement note" "$TMP/p.json" "d['profile']['presentation'] == 'bloc' and d['profile']['source'].startswith('declared') and all('Bloc:' in f['note'] and 'MVN:' not in f['note'] for f in of('PERSIST-001'))"

# --- calibration regressions (references/rules.md, Calibration)
python3 -I "$CHECK" "$FIX/calib_drift" --json > "$TMP/cd.json"
assert "calib_drift: database.dart with a 'Generated by drift_dev' comment is still scanned (TP PERSIST-002)" "$TMP/cd.json" "at('lib/database/database.dart', 12, 'PERSIST-002')"
assert "calib_drift: re-opening into provider state after close() is not PERSIST-006" "$TMP/cd.json" "not at('lib/screens/backup.dart', 16, 'PERSIST-006')"
assert "calib_drift: a database built per tap in a widget still fires (TP PERSIST-006)" "$TMP/cd.json" "at('lib/screens/backup.dart', 30, 'PERSIST-006')"
assert "calib_drift: the provider that owns the database is not PERSIST-006" "$TMP/cd.json" "not [f for f in of('PERSIST-006') if f['file'] == 'lib/database/database.dart']"
assert "calib_drift: modular generated *.drift.dart is skipped" "$TMP/cd.json" "not infile('lib/src/user_queries.drift.dart')"
assert "calib_drift: PRAGMA key with an escaped constant is not PERSIST-001" "$TMP/cd.json" "not at('lib/src/encrypted.dart', 7, 'PERSIST-001')"
assert "calib_drift: a parameter in a SELECT value still fires (TP PERSIST-001 high)" "$TMP/cd.json" "at('lib/src/encrypted.dart', 12, 'PERSIST-001')[0]['severity'] == 'high'"
python3 -I "$CHECK" "$FIX/calib_immich" --json > "$TMP/ci.json"
assert "calib_immich: 'extends \$Drift' databases are detected" "$TMP/ci.json" "d['stats']['drift_databases'] == 2"
assert "calib_immich: PRAGMA user_version = \$to in onUpgrade is not PERSIST-001" "$TMP/ci.json" "not at('lib/data/db/database.dart', 23, 'PERSIST-001')"
assert "calib_immich: loop over a const table map is not PERSIST-001" "$TMP/ci.json" "not at('lib/data/db/database.dart', 41, 'PERSIST-001')"
assert "calib_immich: the same loop over a parameter still fires (TP PERSIST-001 high)" "$TMP/ci.json" "at('lib/data/db/database.dart', 47, 'PERSIST-001')[0]['severity'] == 'high'"
assert "calib_immich: a \$X database without migration still fires (TP PERSIST-002)" "$TMP/ci.json" "[f['line'] for f in of('PERSIST-002')] == [33]"
assert "calib_immich: named constructor in a static init/open() is not PERSIST-006" "$TMP/ci.json" "not at('lib/data/data_controller.dart', 10, 'PERSIST-006') and not at('lib/data/data_controller.dart', 11, 'PERSIST-006')"
assert "calib_immich: a named constructor per call still fires (TP PERSIST-006)" "$TMP/ci.json" "at('lib/data/data_controller.dart', 17, 'PERSIST-006')"
assert "calib_immich: drift_schemas/ present, so no PERSIST-008" "$TMP/ci.json" "'PERSIST-008' not in ids"
python3 -I "$CHECK" "$FIX/calib_lichess" --json > "$TMP/cl.json"
assert "calib_lichess: const table and top-level '?' placeholders are not PERSIST-001" "$TMP/cl.json" "[f['line'] for f in infile('lib/src/model/game_storage.dart')] == [26]"
assert "calib_lichess: private helper fed only constants is low, not high" "$TMP/cl.json" "at('lib/src/db/database.dart', 33, 'PERSIST-001')[0]['severity'] == 'low' and 'constant' in at('lib/src/db/database.dart', 33, 'PERSIST-001')[0]['note']"
assert "calib_lichess: a public method with a LIKE parameter still fires (TP PERSIST-001 high)" "$TMP/cl.json" "at('lib/src/model/game_storage.dart', 26, 'PERSIST-001')[0]['severity'] == 'high'"
assert "calib_lichess: OpenDatabaseOptions with onUpgrade / readOnly is not PERSIST-003" "$TMP/cl.json" "'PERSIST-003' not in ids"

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
python3 -I "$CHECK" "$TMP/nolib" | grep -q '^  no persistence findings$' && pass "no lib/: text report" || bad "no lib/: text report"

[ $fail = 0 ] && echo "ALL flutter-persistence TESTS PASSED" || echo "flutter-persistence: SOME TESTS FAILED"
exit $fail
