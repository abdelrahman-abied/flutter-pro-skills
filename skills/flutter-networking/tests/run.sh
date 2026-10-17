#!/usr/bin/env bash
# Tests for flutter-networking/scripts/check_networking.py.
# No Flutter SDK or pub get needed: the checker is static. bash 3.2 compatible.
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL="$(cd "$HERE/.." && pwd)"
CHECK="$SKILL/scripts/check_networking.py"
FIX="$HERE/fixtures"
TMP="$(mktemp -d "${TMPDIR:-/tmp}/netcheck.XXXXXX")"
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
  pass "check_networking.py parses as Python 3.8"
else
  bad "check_networking.py parses as Python 3.8"
fi

# --- violations fixture: every rule fires
before="$(checksum "$FIX/violations")"
python3 -I "$CHECK" "$FIX/violations" --json > "$TMP/v.json"; rc=$?
[ $rc = 0 ] && pass "violations: exit 0 with findings" || bad "violations: exit 0 with findings (got $rc)"
after="$(checksum "$FIX/violations")"
[ "$before" = "$after" ] && pass "read-only: fixture unchanged" || bad "read-only: fixture unchanged"
for n in 001 002 003 004 005 006 007 008 009 010; do
  assert "violations: NET-$n triggered" "$TMP/v.json" "'NET-$n' in ids"
done
API=lib/core/network/api_client.dart
IMG=lib/core/network/image_downloader.dart
SRC=lib/features/catalog/data/sources/catalog_remote_source.dart
REPO=lib/features/catalog/data/repositories/catalog_repository_impl.dart
NOTI=lib/features/catalog/presentation/notifier/catalog_notifier.dart
BLOC=lib/features/feed/presentation/bloc/feed_bloc.dart
WS=lib/features/chat/data/sources/chat_socket_source.dart
assert "NET-001 medium: shared Dio with no timeouts"           "$TMP/v.json" "at('$API', 5, 'NET-001')[0]['severity'] == 'medium' and 'connectTimeout and receiveTimeout' in at('$API', 5, 'NET-001')[0]['note']"
assert "NET-001 low: only receiveTimeout missing"              "$TMP/v.json" "at('$API', 10, 'NET-001')[0]['severity'] == 'low' and at('$API', 10, 'NET-001')[0]['note'].startswith('missing receiveTimeout.')"
assert "NET-001 low: dart:io HttpClient without a timeout"     "$TMP/v.json" "at('$IMG', 5, 'NET-001')[0]['severity'] == 'low'"
assert "NET-002 per-call Dio in a source (and not also NET-001)" "$TMP/v.json" "'fetchProducts()' in at('$SRC', 6, 'NET-002')[0]['note'] and not at('$SRC', 6, 'NET-001')"
assert "NET-003 local http.Client and HttpClient never closed" "$TMP/v.json" "at('$SRC', 12, 'NET-003') and at('$IMG', 5, 'NET-003') and len(of('NET-003')) == 2"
assert "NET-004 interceptor re-sends without a method check"   "$TMP/v.json" "at('$API', 20, 'NET-004')[0]['severity'] == 'medium' and 'PERSIST-non-idempotent-retry' in at('$API', 20, 'NET-004')[0]['note']"
assert "NET-005 medium: notifier loadMore from a scroll listener" "$TMP/v.json" "at('$NOTI', 15, 'NET-005')[0]['severity'] == 'medium' and 'scroll callback' in at('$NOTI', 15, 'NET-005')[0]['note'] and 'MVN:' in at('$NOTI', 15, 'NET-005')[0]['note']"
assert "NET-005 medium: Bloc on<> without a transformer"       "$TMP/v.json" "'droppable()' in at('$BLOC', 20, 'NET-005')[0]['note'] and at('$BLOC', 20, 'NET-005')[0]['severity'] == 'medium'"
assert "NET-006 field token and inline token"                  "$TMP/v.json" "at('$REPO', 11, 'NET-006') and 'inline' in at('$SRC', 23, 'NET-006')[0]['note']"
assert "NET-006 note: take the token from the caller in data/" "$TMP/v.json" "all('as a parameter from the caller' in f['note'] for f in of('NET-006'))"
assert "NET-007 channel field never closed (data-layer owner note)" "$TMP/v.json" "'_channel.sink.close' in at('$WS', 7, 'NET-007')[0]['note'] and 'ref.onDispose(source.close)' in at('$WS', 7, 'NET-007')[0]['note']"
assert "NET-008 host repeated in a second file, cites the AP"  "$TMP/v.json" "[(f['file'], f['line']) for f in of('NET-008')] == [('$SRC', 7)] and 'AP-hardcoded-config-in-sources' in of('NET-008')[0]['note']"
assert "NET-009 top-level http.get in a source"                "$TMP/v.json" "at('$SRC', 18, 'NET-009')"
assert "NET-010 String parameter in ?q="                       "$TMP/v.json" "'a String parameter' in at('$SRC', 13, 'NET-010')[0]['note']"
assert "notes carry the MVN placement"                         "$TMP/v.json" "all('MVN:' in f['note'] for f in of('NET-001') + of('NET-002') + of('NET-003') + of('NET-009'))"
assert "uses arch_check files[] when installed"                "$TMP/v.json" "d['classification'] == 'arch_check files[]' or d['classification'].startswith('path-based fallback (flutter-architecture')"

# --- JSON contract (CONTRACTS §22, §27)
assert "JSON: schema and top-level keys" "$TMP/v.json" "d['schema'] == 'flutter-pro-skills/networking@1' and set(d) >= {'schema','root','package','profile','classification','stats','findings','suppressed'}"
assert "JSON: finding keys"              "$TMP/v.json" "all(set(f) == {'id','name','severity','file','line','evidence','message','note'} for f in d['findings'])"
assert "JSON: profile and stats keys"    "$TMP/v.json" "set(d['profile']) >= {'presentation','source'} and set(d['stats']) >= {'files','packages','dio_clients','http_clients','interceptors','websockets','cancel_tokens','page_handlers'}"
assert "JSON: severities are known"      "$TMP/v.json" "all(f['severity'] in ('high','medium','low','info') for f in d['findings'])"
assert "JSON: package and packages"      "$TMP/v.json" "d['package'] == 'net_violations' and d['stats']['packages'] == ['dio', 'http', 'web_socket_channel']"

# --- text output (arch_check style)
python3 -I "$CHECK" "$FIX/violations" --max 1 > "$TMP/v.txt"
head -1 "$TMP/v.txt" | grep -q '^== NETWORKING$' && pass "text: header" || bad "text: header"
sed -n 2p "$TMP/v.txt" | grep -q '^  profile: ' && pass "text: profile line" || bad "text: profile line"
sed -n 3p "$TMP/v.txt" | grep -q '^  classification: ' && pass "text: classification line" || bad "text: classification line"
sed -n 4p "$TMP/v.txt" | grep -q '^  scanned: ' && pass "text: scanned line" || bad "text: scanned line"
grep -Eq '^  \[NET-005\] page-fetch-without-guard \(medium\) x2 — ' "$TMP/v.txt" && pass "text: group line format" || bad "text: group line format"
grep -Eq '^      lib/[^ ]+\.dart:[0-9]+  ' "$TMP/v.txt" && pass "text: location lines" || bad "text: location lines"
grep -Eq '^      \.\.\. [0-9]+ more$' "$TMP/v.txt" && pass "text: --max collapses extra locations" || bad "text: --max collapses extra locations"

# --- --files (file list and comma list)
echo "$SRC" > "$TMP/files.txt"
python3 -I "$CHECK" "$FIX/violations" --json --files "$TMP/files.txt" > "$TMP/f.json"
assert "--files: only listed files reported (NET-008 still compares across the project)" "$TMP/f.json" "ids == {'NET-002','NET-003','NET-006','NET-008','NET-009','NET-010'} and all(f['file'] == '$SRC' for f in d['findings'])"
python3 -I "$CHECK" "$FIX/violations" --json --files "$API,$NOTI" > "$TMP/f2.json"
assert "--files: comma list, page callers still resolved in other files" "$TMP/f2.json" "ids == {'NET-001','NET-004','NET-005'} and at('$NOTI', 15, 'NET-005')[0]['severity'] == 'medium'"

# --- clean fixture: safe code and near-misses
python3 -I "$CHECK" "$FIX/clean" --json > "$TMP/c.json"
assert "clean: zero findings" "$TMP/c.json" "d['findings'] == [] and d['suppressed'] == []"
assert "clean: networking code was seen" "$TMP/c.json" "d['stats']['dio_clients'] == 3 and d['stats']['http_clients'] >= 4 and d['stats']['interceptors'] == 2 and d['stats']['websockets'] == 2 and d['stats']['cancel_tokens'] == 3 and d['stats']['page_handlers'] == 2"
python3 -I "$CHECK" "$FIX/clean" > "$TMP/c.txt"
grep -q '^  no networking findings$' "$TMP/c.txt" && pass "clean: text says no findings" || bad "clean: text says no findings"

# --- suppression
python3 -I "$CHECK" "$FIX/suppressed" --json > "$TMP/s.json"
assert "suppress: unsuppressed hit still reported" "$TMP/s.json" "[(f['id'], f['file'], f['line']) for f in d['findings']] == [('NET-001', 'lib/src/line_ignored.dart', 6)]"
assert "suppress: line-above and file comments honoured" "$TMP/s.json" "sorted((s['id'], s['file']) for s in d['suppressed']) == [('NET-001','lib/src/line_ignored.dart'), ('NET-006','lib/src/file_ignored.dart'), ('NET-006','lib/src/file_ignored.dart')]"
assert "suppress: reasons kept" "$TMP/s.json" "all(s['reason'] and s['reason'] != '(no reason given)' for s in d['suppressed'])"
python3 -I "$CHECK" "$FIX/suppressed" | grep -q '^  suppressed: 3 (see --json)$' && pass "suppress: text summary line" || bad "suppress: text summary line"

# --- fallback without the flutter-architecture sibling
mkdir -p "$TMP/lonely/scripts"
cp "$CHECK" "$TMP/lonely/scripts/check_networking.py"
python3 -I "$TMP/lonely/scripts/check_networking.py" "$FIX/violations" --json > "$TMP/fb.json"
assert "fallback: says it used path-based classification" "$TMP/fb.json" "d['classification'].startswith('path-based fallback')"
assert "fallback: every rule still fires" "$TMP/fb.json" "ids == {'NET-%03d' % i for i in range(1, 11)}"
assert "fallback: profile detected from pubspec/folders" "$TMP/fb.json" "d['profile']['presentation'] == 'mvn' and d['profile']['source'].startswith('fallback')"
python3 -I "$TMP/lonely/scripts/check_networking.py" "$FIX/violations" | grep -q '^  classification: path-based fallback' && pass "fallback: text output says so" || bad "fallback: text output says so"
python3 -I "$TMP/lonely/scripts/check_networking.py" "$FIX/clean" --json > "$TMP/fbc.json"
assert "fallback: clean fixture still zero" "$TMP/fbc.json" "d['findings'] == []"

# --- --profile override
python3 -I "$CHECK" "$FIX/violations" --json --profile bloc > "$TMP/p.json"
assert "--profile overrides detection and the placement note" "$TMP/p.json" "d['profile']['presentation'] == 'bloc' and d['profile']['source'].startswith('declared') and all('Bloc:' in f['note'] and 'MVN:' not in f['note'] for f in of('NET-001') + of('NET-006'))"
python3 -I "$CHECK" "$FIX/violations" --json --profile mvvm > "$TMP/p2.json"
assert "--profile mvvm: page note recommends a Command" "$TMP/p2.json" "'Command' in at('$NOTI', 15, 'NET-005')[0]['note']"

# --- calibration regressions (references/rules.md, Calibration)
python3 -I "$CHECK" "$FIX/calib_lichess" --json > "$TMP/cl.json"
CL=lib/src/model/list_controllers.dart
assert "calib_lichess: flag set before the await and checked by the caller is not NET-005" "$TMP/cl.json" "not at('$CL', 22, 'NET-005')"
assert "calib_lichess: the same flag with an unchecked scroll caller still fires (TP medium)" "$TMP/cl.json" "at('$CL', 47, 'NET-005')[0]['severity'] == 'medium'"
assert "calib_lichess: a button-triggered getMore inside itemBuilder is low, not medium (TP low)" "$TMP/cl.json" "at('$CL', 35, 'NET-005')[0]['severity'] == 'low'"
assert "calib_lichess: next single item and explicit page jumps are not page fetches" "$TMP/cl.json" "sorted(f['line'] for f in of('NET-005')) == [35, 47]"
assert "calib_lichess: url_launcher links to the same host are not NET-008" "$TMP/cl.json" "'NET-008' not in ids"
python3 -I "$CHECK" "$FIX/calib_hiddify" --json > "$TMP/ch.json"
assert "calib_hiddify: HttpClient in a Dio adapter factory is not NET-001" "$TMP/ch.json" "not at('lib/core/http/proxy_aware_client.dart', 14, 'NET-001')"
assert "calib_hiddify: a bare HttpClient without timeouts still fires (TP NET-001 low)" "$TMP/ch.json" "at('lib/core/http/proxy_aware_client.dart', 32, 'NET-001')[0]['severity'] == 'low'"
assert "calib_hiddify: '?? CancelToken()' default is not NET-006" "$TMP/ch.json" "not at('lib/features/lists/data/list_downloader.dart', 15, 'NET-006')"
assert "calib_hiddify: an inline CancelToken still fires (TP NET-006)" "$TMP/ch.json" "at('lib/features/lists/data/list_downloader.dart', 20, 'NET-006')"
assert "calib_hiddify: public content hosts are not NET-008" "$TMP/ch.json" "'NET-008' not in ids"
python3 -I "$CHECK" "$FIX/calib_compass" --json > "$TMP/cc.json"
assert "calib_compass: image URLs in data and widgets are not NET-008" "$TMP/cc.json" "not [f for f in of('NET-008') if 'img-cdn-demo.io' in f['note']]"
assert "calib_compass: the API host in two services still fires (TP NET-008)" "$TMP/cc.json" "[(f['file'], f['line']) for f in of('NET-008')] == [('lib/data/services/bookings_service.dart', 8)]"
python3 -I "$CHECK" "$FIX/calib_wonderous" --json > "$TMP/cw.json"
assert "calib_wonderous: an image base path is not NET-008" "$TMP/cw.json" "not infile('lib/logic/data/catalog_data.dart')"
assert "calib_wonderous: a _base… constant repeating the API host fires (false negative fixed)" "$TMP/cw.json" "at('lib/tools/catalog_search_helper.dart', 2, 'NET-008')"
assert "calib_wonderous: app route locations and ids are not NET-010" "$TMP/cw.json" "not infile('lib/router.dart')"
assert "calib_wonderous: a String parameter in an HTTP query still fires (TP NET-010)" "$TMP/cw.json" "at('lib/logic/museum_api_service.dart', 12, 'NET-010')"
python3 -I "$CHECK" "$FIX/calib_samples" --json > "$TMP/cs.json"
assert "calib_samples: a constant in a query string is not NET-010" "$TMP/cs.json" "'NET-010' not in ids"
assert "calib_samples: top-level http calls next to an injected client still fire (TP NET-009)" "$TMP/cs.json" "len(of('NET-009')) == 2 and all('injected http.Client' in f['note'] for f in of('NET-009'))"

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
python3 -I "$CHECK" "$TMP/nolib" | grep -q '^  no networking findings$' && pass "no lib/: text report" || bad "no lib/: text report"

[ $fail = 0 ] && echo "ALL flutter-networking TESTS PASSED" || echo "flutter-networking: SOME TESTS FAILED"
exit $fail
