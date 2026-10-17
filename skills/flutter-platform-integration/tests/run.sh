#!/usr/bin/env bash
# Tests for flutter-platform-integration/scripts/check_platform.py.
# No Flutter SDK or pub get needed: the checker is static. bash 3.2 compatible.
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL="$(cd "$HERE/.." && pwd)"
CHECK="$SKILL/scripts/check_platform.py"
FIX="$HERE/fixtures"
TMP="$(mktemp -d "${TMPDIR:-/tmp}/platcheck.XXXXXX")"
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
  pass "check_platform.py parses as Python 3.8"
else
  bad "check_platform.py parses as Python 3.8"
fi

# --- violations fixture: every rule fires
before="$(checksum "$FIX/violations")"
python3 -I "$CHECK" "$FIX/violations" --json > "$TMP/v.json"; rc=$?
[ $rc = 0 ] && pass "violations: exit 0 with findings" || bad "violations: exit 0 with findings (got $rc)"
after="$(checksum "$FIX/violations")"
[ "$before" = "$after" ] && pass "read-only: fixture unchanged" || bad "read-only: fixture unchanged"
for n in 001 002 003 004 005 006 007 008 009 010 011 012; do
  assert "violations: PLAT-$n triggered" "$TMP/v.json" "'PLAT-$n' in ids"
done
SRC=lib/features/battery/data/sources/battery_platform_source.dart
VIEW=lib/features/battery/presentation/view/battery_view.dart
NOTI=lib/features/battery/presentation/notifier/battery_notifier.dart
FFI=lib/core/ffi/native_text.dart
ISO=lib/core/isolates/thumbnailer.dart
PI=lib/core/plugin/battery_platform.dart
assert "PLAT-001 medium in a State and in a notifier (layered app), once per file" "$TMP/v.json" "at('$VIEW', 15, 'PLAT-001')[0]['severity'] == 'medium' and at('$NOTI', 8, 'PLAT-001')[0]['severity'] == 'medium' and len(of('PLAT-001')) == 2"
assert "PLAT-001 note carries the MVN placement"           "$TMP/v.json" "all('MVN:' in f['note'] for f in of('PLAT-001'))"
assert "PLAT-001 not in the data source"                   "$TMP/v.json" "not at('$SRC', 4, 'PLAT-001')"
assert "PLAT-002 the second copy of a channel name"        "$TMP/v.json" "[(f['file'], f['line']) for f in of('PLAT-002')] == [('$VIEW', 15)] and '$SRC:4' in of('PLAT-002')[0]['note']"
assert "PLAT-003 follows callers to an unguarded onPressed" "$TMP/v.json" "'$VIEW:35' in at('$SRC', 7, 'PLAT-003')[0]['note'] and 'MVN:' in at('$SRC', 7, 'PLAT-003')[0]['note'] and len(of('PLAT-003')) == 1"
assert "PLAT-004 bang on a stored result and a non-null cast" "$TMP/v.json" "at('$SRC', 8, 'PLAT-004') and 'as String' in at('$SRC', 12, 'PLAT-004')[0]['note']"
assert "PLAT-005 medium, State dispose note"                "$TMP/v.json" "at('$VIEW', 23, 'PLAT-005')[0]['severity'] == 'medium' and 'dispose()' in at('$VIEW', 23, 'PLAT-005')[0]['note']"
assert "PLAT-006 high: named, inline and calloc leaks"      "$TMP/v.json" "[f['line'] for f in of('PLAT-006')] == [17, 21, 24] and all(f['severity'] == 'high' for f in of('PLAT-006')) and 'malloc.free(pointer)' in at('$FFI', 17, 'PLAT-006')[0]['note']"
assert "PLAT-007 high: path from the support directory"     "$TMP/v.json" "'getApplicationSupportDirectory' in at('$FFI', 34, 'PLAT-007')[0]['note']"
assert "PLAT-008 low: State handler never cleared"          "$TMP/v.json" "at('$VIEW', 26, 'PLAT-008')[0]['severity'] == 'low'"
assert "PLAT-009 medium implements, low setter without verify" "$TMP/v.json" "at('$PI', 21, 'PLAT-009')[0]['severity'] == 'medium' and at('$PI', 12, 'PLAT-009')[0]['severity'] == 'low'"
assert "PLAT-010 high: Isolate.spawn entry uses a channel"  "$TMP/v.json" "at('$ISO', 8, 'PLAT-010')[0]['severity'] == 'high'"
assert "PLAT-011 and PLAT-012 on the startup request"       "$TMP/v.json" "at('lib/main.dart', 7, 'PLAT-011') and at('lib/main.dart', 7, 'PLAT-012') and 'MVN:' in at('lib/main.dart', 7, 'PLAT-012')[0]['note']"
assert "uses arch_check files[] when installed"             "$TMP/v.json" "d['classification'] == 'arch_check files[]' or d['classification'].startswith('path-based fallback (flutter-architecture')"

# --- JSON contract (CONTRACTS §22, §31)
assert "JSON: schema and top-level keys" "$TMP/v.json" "d['schema'] == 'flutter-pro-skills/platform@1' and set(d) >= {'schema','root','package','profile','classification','stats','findings','suppressed'}"
assert "JSON: finding keys"              "$TMP/v.json" "all(set(f) == {'id','name','severity','file','line','evidence','message','note'} for f in d['findings'])"
assert "JSON: profile and stats keys"    "$TMP/v.json" "set(d['profile']) >= {'presentation','source'} and set(d['stats']) >= {'files','method_channels','event_channels','message_channels','pigeon_apis','ffi_files','native_allocations','dynamic_libraries','platform_interfaces','isolate_entries','permission_requests','skipped_generated'}"
assert "JSON: severities are known"      "$TMP/v.json" "all(f['severity'] in ('high','medium','low','info') for f in d['findings'])"
assert "JSON: package and counts"        "$TMP/v.json" "d['package'] == 'plat_violations' and d['stats']['method_channels'] == 4 and d['stats']['event_channels'] == 1 and d['stats']['native_allocations'] == 3"

# --- text output (arch_check style)
python3 -I "$CHECK" "$FIX/violations" --max 1 > "$TMP/v.txt"
head -1 "$TMP/v.txt" | grep -q '^== PLATFORM$' && pass "text: header" || bad "text: header"
sed -n 2p "$TMP/v.txt" | grep -q '^  profile: ' && pass "text: profile line" || bad "text: profile line"
sed -n 3p "$TMP/v.txt" | grep -q '^  classification: ' && pass "text: classification line" || bad "text: classification line"
sed -n 4p "$TMP/v.txt" | grep -q '^  scanned: ' && pass "text: scanned line" || bad "text: scanned line"
grep -Eq '^  \[PLAT-006\] native-memory-not-freed \(high\) x3 — ' "$TMP/v.txt" && pass "text: group line format" || bad "text: group line format"
grep -Eq '^      lib/[^ ]+\.dart:[0-9]+  ' "$TMP/v.txt" && pass "text: location lines" || bad "text: location lines"
grep -Eq '^      \.\.\. [0-9]+ more$' "$TMP/v.txt" && pass "text: --max collapses extra locations" || bad "text: --max collapses extra locations"
head -5 "$TMP/v.txt" | sed -n 5p | grep -q '(high)' && pass "text: high groups first" || bad "text: high groups first"

# --- --files (file list and comma list)
echo "$SRC" > "$TMP/files.txt"
python3 -I "$CHECK" "$FIX/violations" --json --files "$TMP/files.txt" > "$TMP/f.json"
assert "--files: only listed files reported (callers still resolved in other files)" "$TMP/f.json" "ids == {'PLAT-003','PLAT-004'} and all(f['file'] == '$SRC' for f in d['findings'])"
python3 -I "$CHECK" "$FIX/violations" --json --files "$VIEW,lib/main.dart" > "$TMP/f2.json"
assert "--files: comma list, channel names still compared project-wide" "$TMP/f2.json" "ids == {'PLAT-001','PLAT-002','PLAT-005','PLAT-008','PLAT-011','PLAT-012'}"

# --- clean fixture: safe code and near-misses
python3 -I "$CHECK" "$FIX/clean" --json > "$TMP/c.json"
assert "clean: zero findings" "$TMP/c.json" "d['findings'] == [] and d['suppressed'] == []"
assert "clean: platform code was seen" "$TMP/c.json" "d['stats']['method_channels'] == 2 and d['stats']['event_channels'] == 1 and d['stats']['native_allocations'] >= 6 and d['stats']['isolate_entries'] == 2 and d['stats']['platform_interfaces'] == 1 and d['stats']['permission_requests'] == 1 and d['stats']['pigeon_apis'] == 1"
assert "clean: Pigeon dartOut, ffigen output and a Pigeon banner are skipped" "$TMP/c.json" "d['stats']['skipped_generated'] == 3 and not infile('lib/src/messages.dart') and not infile('lib/src/native_bindings.dart')"
python3 -I "$CHECK" "$FIX/clean" > "$TMP/c.txt"
grep -q '^  no platform findings$' "$TMP/c.txt" && pass "clean: text says no findings" || bad "clean: text says no findings"

# --- suppression
python3 -I "$CHECK" "$FIX/suppressed" --json > "$TMP/s.json"
assert "suppress: unsuppressed hit still reported" "$TMP/s.json" "[(f['id'], f['file'], f['line']) for f in d['findings']] == [('PLAT-006', 'lib/src/line_ignored.dart', 8)]"
assert "suppress: line-above and file comments honoured" "$TMP/s.json" "sorted((s['id'], s['file']) for s in d['suppressed']) == [('PLAT-004','lib/src/file_ignored.dart'), ('PLAT-004','lib/src/file_ignored.dart'), ('PLAT-006','lib/src/line_ignored.dart')]"
assert "suppress: reasons kept" "$TMP/s.json" "all(s['reason'] and s['reason'] != '(no reason given)' for s in d['suppressed'])"
python3 -I "$CHECK" "$FIX/suppressed" | grep -q '^  suppressed: 3 (see --json)$' && pass "suppress: text summary line" || bad "suppress: text summary line"

# --- fallback without the flutter-architecture sibling
mkdir -p "$TMP/lonely/scripts"
cp "$CHECK" "$TMP/lonely/scripts/check_platform.py"
python3 -I "$TMP/lonely/scripts/check_platform.py" "$FIX/violations" --json > "$TMP/fb.json"
assert "fallback: says it used path-based classification" "$TMP/fb.json" "d['classification'].startswith('path-based fallback')"
assert "fallback: every rule still fires" "$TMP/fb.json" "ids == {'PLAT-%03d' % i for i in range(1, 13)}"
assert "fallback: profile detected from pubspec/folders" "$TMP/fb.json" "d['profile']['presentation'] == 'mvn' and d['profile']['source'].startswith('fallback')"
python3 -I "$TMP/lonely/scripts/check_platform.py" "$FIX/violations" | grep -q '^  classification: path-based fallback' && pass "fallback: text output says so" || bad "fallback: text output says so"
python3 -I "$TMP/lonely/scripts/check_platform.py" "$FIX/clean" --json > "$TMP/fbc.json"
assert "fallback: clean fixture still zero" "$TMP/fbc.json" "d['findings'] == []"

# --- --profile override
python3 -I "$CHECK" "$FIX/violations" --json --profile bloc > "$TMP/p.json"
assert "--profile overrides detection and the placement note" "$TMP/p.json" "d['profile']['presentation'] == 'bloc' and d['profile']['source'].startswith('declared') and all('Bloc:' in f['note'] and 'MVN:' not in f['note'] for f in of('PLAT-001') + of('PLAT-003'))"
python3 -I "$CHECK" "$FIX/violations" --json --profile mvvm > "$TMP/p2.json"
assert "--profile mvvm: the mapping note names Result" "$TMP/p2.json" "'Result' in at('$SRC', 7, 'PLAT-003')[0]['note']"

# --- calibration regressions (references/rules.md, Calibration)
python3 -I "$CHECK" "$FIX/calib_immich" --json > "$TMP/ci.json"
assert "calib_immich: a Pigeon HostApi built in main() is composition root, not PLAT-001" "$TMP/ci.json" "not infile('lib/main.dart')"
assert "calib_immich: the same HostApi built in a State still fires (TP medium)" "$TMP/ci.json" "at('lib/presentation/pages/upload_page.dart', 13, 'PLAT-001')[0]['severity'] == 'medium'"
assert "calib_immich: Pigeon APIs read from pigeon/*.dart" "$TMP/ci.json" "d['stats']['pigeon_apis'] == 1"
python3 -I "$CHECK" "$FIX/calib_hiddify" --json > "$TMP/ch.json"
assert "calib_hiddify: a keepAlive notifier in core/ reading the host is not PLAT-001" "$TMP/ch.json" "not infile('lib/core/paths/app_paths_provider.dart')"
assert "calib_hiddify: a presentation notifier with a channel still fires (TP medium)" "$TMP/ch.json" "at('lib/features/tunnel/presentation/tunnel_toggle_notifier.dart', 8, 'PLAT-001')[0]['severity'] == 'medium'"
assert "calib_hiddify: the host channel name in two files fires (TP PLAT-002)" "$TMP/ch.json" "[(f['file'], f['line']) for f in of('PLAT-002')] == [('lib/features/tunnel/data/tunnel_repository.dart', 4)]"
assert "calib_hiddify: an environment check in the condition is not PLAT-007" "$TMP/ch.json" "'PLAT-007' not in ids"
assert "calib_hiddify: strings passed inline to native fire (TP PLAT-006), the finally helper does not" "$TMP/ch.json" "[f['line'] for f in of('PLAT-006')] == [22, 22]"
python3 -I "$CHECK" "$FIX/calib_plugins" --json > "$TMP/cp.json"
NA=lib/src/native_args.dart
MC=lib/src/method_channel_recorder.dart
assert "calib_plugins: strings stored into a returned native array are not PLAT-006" "$TMP/cp.json" "not at('$NA', 13, 'PLAT-006')"
assert "calib_plugins: a pointer handed to a finalizer inside assert() is not PLAT-006" "$TMP/cp.json" "not [f for f in of('PLAT-006') if f['line'] > 25]"
assert "calib_plugins: an inline string to native still fires (TP PLAT-006)" "$TMP/cp.json" "[f['line'] for f in of('PLAT-006')] == [21]"
assert "calib_plugins: overrides called through the interface are not PLAT-003" "$TMP/cp.json" "not at('$MC', 10, 'PLAT-003') and not at('$MC', 15, 'PLAT-003')"
assert "calib_plugins: a fire-and-forget call in a setter still fires (TP PLAT-003)" "$TMP/cp.json" "[f['line'] for f in of('PLAT-003')] == [25]"
assert "calib_plugins: 'as T' on a type parameter is not PLAT-004; 'as String' is" "$TMP/cp.json" "[f['line'] for f in of('PLAT-004')] == [22]"
assert "calib_plugins: a verified platform interface is clean" "$TMP/cp.json" "'PLAT-009' not in ids"
python3 -I "$CHECK" "$FIX/calib_samples" --json > "$TMP/cs.json"
CD=lib/src/counter_demo.dart
assert "calib_samples: the bang after 'final x = await' is found (false negative fixed)" "$TMP/cs.json" "at('lib/src/counter_channel.dart', 8, 'PLAT-004')"
assert "calib_samples: callers inside try/catch handle the wrapper's errors" "$TMP/cs.json" "not [f for f in of('PLAT-003') if f['file'] == 'lib/src/counter_channel.dart']"
assert "calib_samples: no data layer, so PLAT-001 is low" "$TMP/cs.json" "at('$CD', 20, 'PLAT-001')[0]['severity'] == 'low'"
assert "calib_samples: handler re-registered in didChangeDependencies (TP low)" "$TMP/cs.json" "'didChangeDependencies' in at('$CD', 20, 'PLAT-008')[0]['note']"
assert "calib_samples: ChangeNotifier handler note names its dispose()" "$TMP/cs.json" "'ChangeNotifier' in at('$CD', 45, 'PLAT-008')[0]['note']"
assert "calib_samples: fire-and-forget invoke in a model (TP low)" "$TMP/cs.json" "at('$CD', 52, 'PLAT-003')[0]['severity'] == 'low'"

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
python3 -I "$CHECK" "$TMP/nolib" | grep -q '^  no platform findings$' && pass "no lib/: text report" || bad "no lib/: text report"

[ $fail = 0 ] && echo "ALL flutter-platform-integration TESTS PASSED" || echo "flutter-platform-integration: SOME TESTS FAILED"
exit $fail
