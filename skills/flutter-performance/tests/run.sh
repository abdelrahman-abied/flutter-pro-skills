#!/usr/bin/env bash
# Tests for flutter-performance/scripts/check_performance.py.
# No Flutter SDK or pub get needed: the checker is static. bash 3.2 compatible.
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL="$(cd "$HERE/.." && pwd)"
CHECK="$SKILL/scripts/check_performance.py"
FIX="$HERE/fixtures"
TMP="$(mktemp -d "${TMPDIR:-/tmp}/perfcheck.XXXXXX")"
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
def sev(rid):
    return sorted(f['severity'] for f in of(rid))
def infile(rel, rid=None):
    return [f for f in d['findings'] if f['file'].endswith(rel) and (rid is None or f['id'] == rid)]
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
  pass "check_performance.py parses as Python 3.8"
else
  bad "check_performance.py parses as Python 3.8"
fi

# --- violations fixture: every rule fires
before="$(checksum "$FIX/violations")"
python3 -I "$CHECK" "$FIX/violations" --json > "$TMP/v.json"; rc=$?
[ $rc = 0 ] && pass "violations: exit 0 with findings" || bad "violations: exit 0 with findings (got $rc)"
after="$(checksum "$FIX/violations")"
[ "$before" = "$after" ] && pass "read-only: fixture unchanged" || bad "read-only: fixture unchanged"
for n in 001 002 003 004 005 006 007 008 009 010 011; do
  assert "violations: PERF-$n triggered" "$TMP/v.json" "'PERF-$n' in ids"
done
P=lib/features/feed/presentation
assert "PERF-001 medium for a ListView over state data"   "$TMP/v.json" "at('$P/view/feed_view.dart', 21, 'PERF-001')[0]['severity'] == 'medium'"
assert "PERF-001 note follows the mvn profile"            "$TMP/v.json" "'MVN:' in of('PERF-001')[0]['note']"
assert "PERF-002 medium for a nested builder list"        "$TMP/v.json" "at('$P/view/feed_view.dart', 31, 'PERF-002')[0]['severity'] == 'medium' and 'SingleChildScrollView' in of('PERF-002')[0]['note']"
assert "PERF-003 inside an itemBuilder"                   "$TMP/v.json" "at('$P/view/gallery_view.dart', 21, 'PERF-003')"
assert "PERF-004 inline and one hop (PostTile)"           "$TMP/v.json" "sorted(f['file'].split('/')[-1] for f in of('PERF-004')) == ['gallery_view.dart', 'post_tile.dart'] and 'memCacheWidth' in infile('post_tile.dart', 'PERF-004')[0]['note'] and 'PostTile' in infile('post_tile.dart', 'PERF-004')[0]['note']"
assert "PERF-005 animated and per-item Opacity, both low" "$TMP/v.json" "sev('PERF-005') == ['low', 'low'] and infile('fade_banner.dart', 'PERF-005') and 'AnimatedBuilder' in infile('fade_banner.dart', 'PERF-005')[0]['note']"
assert "PERF-006 BackdropFilter medium, ShaderMask/ClipPath low" "$TMP/v.json" "sev('PERF-006') == ['low', 'low', 'medium'] and at('$P/view/gallery_view.dart', 26, 'PERF-006')[0]['severity'] == 'medium'"
assert "PERF-007 GlobalKey in build"                      "$TMP/v.json" "at('$P/view/feed_view.dart', 13, 'PERF-007')"
assert "PERF-008 suggests select for the one field"       "$TMP/v.json" "'bannerNotifierProvider.select((s) => s.title)' in of('PERF-008')[0]['note']"
assert "PERF-009 scroll medium, animation low"            "$TMP/v.json" "sev('PERF-009') == ['low', 'medium'] and at('$P/widget/fade_banner.dart', 19, 'PERF-009')[0]['severity'] == 'medium'"
assert "PERF-009 animation note has no scroll advice"     "$TMP/v.json" "'MVN:' not in at('$P/widget/fade_banner.dart', 18, 'PERF-009')[0]['note']"
assert "PERF-010 notes the in-place mutation"             "$TMP/v.json" "'mutates' in of('PERF-010')[0]['note']"
assert "PERF-011 info in the data source"                 "$TMP/v.json" "of('PERF-011')[0]['severity'] == 'info' and of('PERF-011')[0]['file'].endswith('feed_remote_source.dart')"
assert "uses arch_check files[] when installed"           "$TMP/v.json" "d['classification'] == 'arch_check files[]' or d['classification'].startswith('path-based fallback (flutter-architecture')"

# --- JSON contract (CONTRACTS §22)
assert "JSON: schema and top-level keys" "$TMP/v.json" "d['schema'] == 'flutter-pro-skills/performance@1' and set(d) >= {'schema','root','package','profile','classification','stats','findings','suppressed'}"
assert "JSON: finding keys"              "$TMP/v.json" "all(set(f) == {'id','name','severity','file','line','evidence','message','note'} for f in d['findings'])"
assert "JSON: profile and stats keys"    "$TMP/v.json" "set(d['profile']) >= {'presentation','source'} and set(d['stats']) >= {'files','item_builders','item_widgets','scrollables','images','build_methods'}"
assert "JSON: severities are known"      "$TMP/v.json" "all(f['severity'] in ('high','medium','low','info') for f in d['findings'])"
assert "JSON: package from pubspec"      "$TMP/v.json" "d['package'] == 'perf_violations'"

# --- text output
python3 -I "$CHECK" "$FIX/violations" --max 1 > "$TMP/v.txt"
head -1 "$TMP/v.txt" | grep -q '^== PERFORMANCE$' && pass "text: header" || bad "text: header"
sed -n 2p "$TMP/v.txt" | grep -q '^  profile: ' && pass "text: profile line" || bad "text: profile line"
sed -n 3p "$TMP/v.txt" | grep -q '^  classification: ' && pass "text: classification line" || bad "text: classification line"
sed -n 4p "$TMP/v.txt" | grep -q '^  scanned: ' && pass "text: scanned line" || bad "text: scanned line"
grep -Eq '^  \[PERF-001\] eager-list-over-data \(medium\) x[0-9]+ — ' "$TMP/v.txt" && pass "text: group line format" || bad "text: group line format"
grep -Eq '^      lib/[^ ]+\.dart:[0-9]+  ' "$TMP/v.txt" && pass "text: location lines" || bad "text: location lines"
grep -Eq '^      \.\.\. [0-9]+ more$' "$TMP/v.txt" && pass "text: --max collapses extra locations" || bad "text: --max collapses extra locations"

# --- --files (file list and comma list)
echo "$P/widget/post_tile.dart" > "$TMP/files.txt"
python3 -I "$CHECK" "$FIX/violations" --json --files "$TMP/files.txt" > "$TMP/f.json"
assert "--files: list file, one-hop item widget still found" "$TMP/f.json" "ids == {'PERF-004', 'PERF-006'} and all(f['file'].endswith('post_tile.dart') for f in d['findings'])"
python3 -I "$CHECK" "$FIX/violations" --json --files "$P/widget/fade_banner.dart,lib/features/feed/data/sources/feed_remote_source.dart" > "$TMP/f2.json"
assert "--files: comma list" "$TMP/f2.json" "ids == {'PERF-005', 'PERF-009', 'PERF-011'}"

# --- clean fixture: fast code and near-misses
before="$(checksum "$FIX/clean")"
python3 -I "$CHECK" "$FIX/clean" --json > "$TMP/c.json"
assert "clean: zero findings" "$TMP/c.json" "d['findings'] == [] and d['suppressed'] == []"
assert "clean: lists and images were seen" "$TMP/c.json" "d['stats']['item_builders'] >= 3 and d['stats']['images'] >= 4"
python3 -I "$CHECK" "$FIX/clean" > "$TMP/c.txt"
grep -q '^  no performance findings$' "$TMP/c.txt" && pass "clean: text says no findings" || bad "clean: text says no findings"
[ "$before" = "$(checksum "$FIX/clean")" ] && pass "read-only: clean fixture unchanged" || bad "read-only: clean fixture unchanged"

# --- suppression
python3 -I "$CHECK" "$FIX/suppressed" --json > "$TMP/s.json"
assert "suppress: unsuppressed hit still reported" "$TMP/s.json" "[(f['id'], f['file'], f['line']) for f in d['findings']] == [('PERF-001', 'lib/src/line_ignored.dart', 21)]"
assert "suppress: line-above, same-line and file comments honoured" "$TMP/s.json" "sorted((s['id'], s['file']) for s in d['suppressed']) == [('PERF-001','lib/src/line_ignored.dart'), ('PERF-003','lib/src/line_ignored.dart'), ('PERF-005','lib/src/file_ignored.dart'), ('PERF-005','lib/src/file_ignored.dart')]"
assert "suppress: reasons kept" "$TMP/s.json" "all(s['reason'] and s['reason'] != '(no reason given)' for s in d['suppressed'])"
python3 -I "$CHECK" "$FIX/suppressed" | grep -q '^  suppressed: 4 (see --json)$' && pass "suppress: text summary line" || bad "suppress: text summary line"

# --- calibration regressions (one fixture per false-positive cause; related true positives still fire)
python3 -I "$CHECK" "$FIX/calib_wonderous" --json > "$TMP/cw.json"
assert "calib_wonderous: fixed-count List.generate grid is not PERF-001" "$TMP/cw.json" "not [f for f in of('PERF-001') if f['line'] < 25]"
assert "calib_wonderous: TP unbounded log ListView still PERF-001 medium" "$TMP/cw.json" "[(f['line'], f['severity']) for f in of('PERF-001')] == [(30, 'medium')]"
assert "calib_wonderous: ValueNotifier *Controller listener is not PERF-009" "$TMP/cw.json" "not [f for f in of('PERF-009') if 'panelController' in f['note']]"
assert "calib_wonderous: TP ScrollController listener still PERF-009 medium" "$TMP/cw.json" "[(f['severity'], '_list' in f['note']) for f in of('PERF-009')] == [('medium', True)]"
python3 -I "$CHECK" "$FIX/calib_immich" --json > "$TMP/ci.json"
assert "calib_immich: TextEditingController listeners are not PERF-009" "$TMP/ci.json" "of('PERF-009') == []"
assert "calib_immich: TP hook form key still PERF-007 with the hooks fix" "$TMP/ci.json" "len(of('PERF-007')) == 1 and 'useMemoized' in of('PERF-007')[0]['note']"
python3 -I "$CHECK" "$FIX/calib_lichess" --json > "$TMP/cl.json"
assert "calib_lichess: ref.watch(x).field in a Notifier build is not PERF-008" "$TMP/cl.json" "not [f for f in of('PERF-008') if f['line'] < 28]"
assert "calib_lichess: TP ConsumerWidget ref.watch(prefs).isSoundEnabled still PERF-008" "$TMP/cl.json" "[f['line'] for f in of('PERF-008')] == [33]"
assert "calib_lichess: TP PageController listener is a scroll listener (medium)" "$TMP/cl.json" "[f['severity'] for f in of('PERF-009')] == ['medium']"
python3 -I "$CHECK" "$FIX/calib_riverpod_todos" --json > "$TMP/ct.json"
assert "calib_riverpod_todos: mixed header + data ListView is low, not medium" "$TMP/ct.json" "at('lib/main.dart', 13, 'PERF-001')[0]['severity'] == 'low'"
assert "calib_riverpod_todos: TP data-only ListView still medium" "$TMP/ct.json" "at('lib/main.dart', 34, 'PERF-001')[0]['severity'] == 'medium'"

# --- fallback without the flutter-architecture sibling
mkdir -p "$TMP/lonely/scripts"
cp "$CHECK" "$TMP/lonely/scripts/check_performance.py"
python3 -I "$TMP/lonely/scripts/check_performance.py" "$FIX/violations" --json > "$TMP/fb.json"
assert "fallback: says it used path-based classification" "$TMP/fb.json" "d['classification'].startswith('path-based fallback')"
assert "fallback: every rule still fires" "$TMP/fb.json" "ids == {'PERF-%03d' % i for i in range(1, 12)}"
assert "fallback: profile detected from pubspec/folders" "$TMP/fb.json" "d['profile']['presentation'] == 'mvn' and d['profile']['source'].startswith('fallback')"
python3 -I "$TMP/lonely/scripts/check_performance.py" "$FIX/violations" | grep -q '^  classification: path-based fallback' && pass "fallback: text output says so" || bad "fallback: text output says so"
python3 -I "$TMP/lonely/scripts/check_performance.py" "$FIX/clean" --json > "$TMP/fbc.json"
assert "fallback: clean fixture still zero" "$TMP/fbc.json" "d['findings'] == []"

# --- --profile override
python3 -I "$CHECK" "$FIX/violations" --json --profile bloc > "$TMP/p.json"
assert "--profile overrides detection and the fix hint" "$TMP/p.json" "d['profile']['presentation'] == 'bloc' and d['profile']['source'].startswith('declared') and 'Bloc:' in of('PERF-001')[0]['note'] and 'Bloc:' in of('PERF-008')[0]['note']"

# --- FPS_ARCH_JSON reuse (CONTRACTS §20): a matching document is used, a foreign one is ignored
ARCH="$SKILL/../flutter-architecture/scripts/arch_check.py"
if [ -f "$ARCH" ]; then
  python3 -I "$ARCH" "$FIX/violations" --json > "$TMP/arch.json"
  FPS_ARCH_JSON="$TMP/arch.json" python3 -I "$CHECK" "$FIX/violations" --json > "$TMP/e.json"
  assert "FPS_ARCH_JSON: reused for the same root" "$TMP/e.json" "d['classification'] == 'arch_check files[]' and 'PERF-011' in ids"
  FPS_ARCH_JSON="$TMP/arch.json" python3 -I "$CHECK" "$FIX/clean" --json > "$TMP/e2.json"
  assert "FPS_ARCH_JSON: ignored for another root" "$TMP/e2.json" "d['findings'] == [] and d['profile']['presentation'] != 'mvn'"
else
  echo "SKIP FPS_ARCH_JSON (flutter-architecture not installed)"
fi

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
python3 -I "$CHECK" "$TMP/nolib" | grep -q '^  no performance findings$' && pass "no lib/: text report" || bad "no lib/: text report"

[ $fail = 0 ] && echo "ALL flutter-performance TESTS PASSED" || echo "flutter-performance: SOME TESTS FAILED"
exit $fail
