#!/usr/bin/env bash
# Tests for flutter-release/scripts/check_release.py.
# No Flutter SDK, Android SDK, Xcode or pub get needed: the checker is static. bash 3.2 compatible.
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL="$(cd "$HERE/.." && pwd)"
CHECK="$SKILL/scripts/check_release.py"
FIX="$HERE/fixtures"
TMP="$(mktemp -d "${TMPDIR:-/tmp}/relcheck.XXXXXX")"
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
def of(rid, sev=None):
    return [f for f in d['findings'] if f['id'] == rid and (sev is None or f['severity'] == sev)]
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
  pass "check_release.py parses as Python 3.8"
else
  bad "check_release.py parses as Python 3.8"
fi

# --- violations fixture: every rule fires
before="$(checksum "$FIX/violations")"
python3 -I "$CHECK" "$FIX/violations" --json > "$TMP/v.json"; rc=$?
[ $rc = 0 ] && pass "violations: exit 0 with findings" || bad "violations: exit 0 with findings (got $rc)"
after="$(checksum "$FIX/violations")"
[ "$before" = "$after" ] && pass "read-only: fixture unchanged" || bad "read-only: fixture unchanged"
for n in 001 002 003 004 005 006 007 008 009 010 011 012; do
  assert "violations: REL-$n triggered" "$TMP/v.json" "'REL-$n' in ids"
done
G=android/app/build.gradle
PBX=ios/Runner.xcodeproj/project.pbxproj
EP=lib/core/network/endpoints.dart
REL=.github/workflows/release.yml
assert "REL-001 high: release buildType signed with signingConfigs.debug" "$TMP/v.json" "at('$G', 48, 'REL-001')[0]['severity'] == 'high' and 'Play App Signing' in at('$G', 48, 'REL-001')[0]['note']"
assert "REL-002 high: an unignored .jks on disk"                  "$TMP/v.json" "at('android/app/upload-keystore.jks', 1, 'REL-002')[0]['severity'] == 'high' and 'rotate' in of('REL-002', 'high')[0]['note']"
assert "REL-002 low: key.properties used but no .gitignore pattern" "$TMP/v.json" "at('$G', 7, 'REL-002')[0]['severity'] == 'low'"
assert "REL-003 medium: com.example on Android and iOS"            "$TMP/v.json" "at('$G', 17, 'REL-003')[0]['severity'] == 'medium' and at('$PBX', 16, 'REL-003') and len(of('REL-003')) == 2"
assert "REL-003: the RunnerTests bundle id is not reported twice"   "$TMP/v.json" "not infile('$PBX')[1:]"
assert "REL-004 medium: Android flavor without an iOS scheme"       "$TMP/v.json" "'\"staging\" has no iOS scheme' in at('$G', 30, 'REL-004')[0]['note']"
assert "REL-004 medium: iOS scheme without an Android flavor"       "$TMP/v.json" "at('ios/Runner.xcodeproj/xcshareddata/xcschemes/qa.xcscheme', 1, 'REL-004')[0]['severity'] == 'medium'"
assert "REL-004 low: entrypoint matching no flavor (prod/dev match)" "$TMP/v.json" "[f['file'] for f in of('REL-004', 'low')] == ['lib/main_demo.dart']"
assert "REL-005: ternary of URLs, if-branch endpoint, dart.vm.product" "$TMP/v.json" "sorted(f['line'] for f in of('REL-005')) == [4, 9, 16] and all(f['file'] == '$EP' for f in of('REL-005'))"
assert "REL-005 notes carry the profile's injection point"          "$TMP/v.json" "all('ProviderScope(overrides' in f['note'] for f in of('REL-005'))"
assert "REL-006: view and data source read the flavor, cite the AP" "$TMP/v.json" "sorted(f['file'] for f in of('REL-006')) == ['lib/features/cart/data/sources/cart_remote_source.dart', 'lib/features/cart/presentation/view/cart_view.dart'] and all('AP-hardcoded-config-in-sources' in f['note'] for f in of('REL-006'))"
assert "REL-007: overlay medium, grid and debugPaint low"           "$TMP/v.json" "at('lib/app.dart', 9, 'REL-007')[0]['severity'] == 'medium' and at('lib/app.dart', 10, 'REL-007')[0]['severity'] == 'low' and at('lib/main_dev.dart', 7, 'REL-007')[0]['severity'] == 'low'"
assert "REL-008 medium: targetSdkVersion 33, dated threshold"       "$TMP/v.json" "'since 20' in at('$G', 19, 'REL-008')[0]['note']"
assert "REL-009: local_auth without NSFaceIDUsageDescription only"  "$TMP/v.json" "[(f['file'], f['line']) for f in of('REL-009')] == [('pubspec.yaml', 14)] and 'NSFaceIDUsageDescription' in of('REL-009')[0]['note']"
assert "REL-010 high: pull_request_target checks out the PR head"   "$TMP/v.json" "at('.github/workflows/pr.yml', 12, 'REL-010')[0]['severity'] == 'high' and 'secrets' in at('.github/workflows/pr.yml', 12, 'REL-010')[0]['note']"
assert "REL-011: env-mapped secret and direct secret echoed (not the piped decode)" "$TMP/v.json" "sorted((f['file'], f['line']) for f in of('REL-011')) == [('$REL', 17), ('$REL', 19), ('codemagic.yaml', 12)]"
assert "REL-012 high: artifact path covers the decoded keystore"    "$TMP/v.json" "at('$REL', 24, 'REL-012')[0]['severity'] == 'high' and at('codemagic.yaml', 17, 'REL-012')"
assert "REL-012 low: keystore left on a self-hosted runner"         "$TMP/v.json" "at('$REL', 16, 'REL-012')[0]['severity'] == 'low'"
assert "stats: platforms, flavors, intent, CI files"                "$TMP/v.json" "d['stats']['app_kind'] == 'app' and d['stats']['flavors']['android'] == ['dev', 'prod', 'staging'] and d['stats']['flavors']['ios'] == ['dev', 'prod', 'qa'] and 'flavors' in d['stats']['release_intent'] and len(d['stats']['ci_files']) == 3"
assert "uses arch_check files[] when installed"                     "$TMP/v.json" "d['classification'] == 'arch_check files[]' or d['classification'].startswith('path-based fallback (flutter-architecture')"

# --- JSON contract (CONTRACTS §22, §29)
assert "JSON: schema and top-level keys" "$TMP/v.json" "d['schema'] == 'flutter-pro-skills/release@1' and set(d) >= {'schema','root','package','profile','classification','stats','findings','suppressed'}"
assert "JSON: finding keys"              "$TMP/v.json" "all(set(f) == {'id','name','severity','file','line','evidence','message','note'} for f in d['findings'])"
assert "JSON: profile and stats keys"    "$TMP/v.json" "set(d['profile']) >= {'presentation','source'} and set(d['stats']) >= {'files','platforms','platform_rules','app_kind','release_intent','flavors','build_files','ci_files','skipped_generated'}"
assert "JSON: severities are known"      "$TMP/v.json" "all(f['severity'] in ('high','medium','low','info') for f in d['findings'])"
assert "JSON: package"                   "$TMP/v.json" "d['package'] == 'rel_violations'"

# --- text output
python3 -I "$CHECK" "$FIX/violations" --max 1 > "$TMP/v.txt"
head -1 "$TMP/v.txt" | grep -q '^== RELEASE$' && pass "text: header" || bad "text: header"
sed -n 2p "$TMP/v.txt" | grep -q '^  profile: ' && pass "text: profile line" || bad "text: profile line"
sed -n 3p "$TMP/v.txt" | grep -q '^  classification: ' && pass "text: classification line" || bad "text: classification line"
sed -n 4p "$TMP/v.txt" | grep -q '^  scanned: .*release intent: ' && pass "text: scanned line" || bad "text: scanned line"
grep -Eq '^  \[REL-005\] environment-by-build-mode \(medium\) x3 — ' "$TMP/v.txt" && pass "text: group line format" || bad "text: group line format"
grep -Eq '^      [^ ]+:[0-9]+  ' "$TMP/v.txt" && pass "text: location lines" || bad "text: location lines"
grep -Eq '^      \.\.\. [0-9]+ more$' "$TMP/v.txt" && pass "text: --max collapses extra locations" || bad "text: --max collapses extra locations"

# --- --files (file list and comma list)
printf '%s\n' "$REL" > "$TMP/files.txt"
python3 -I "$CHECK" "$FIX/violations" --json --files "$TMP/files.txt" > "$TMP/f.json"
assert "--files: only the listed workflow is reported" "$TMP/f.json" "ids == {'REL-011','REL-012'} and all(f['file'] == '$REL' for f in d['findings'])"
python3 -I "$CHECK" "$FIX/violations" --json --files "lib/main_demo.dart,$G" > "$TMP/f2.json"
assert "--files: comma list, flavors still compared across platforms" "$TMP/f2.json" "ids == {'REL-001','REL-002','REL-003','REL-004','REL-008'} and at('$G', 30, 'REL-004') and at('lib/main_demo.dart', 1, 'REL-004')"

# --- clean fixture: safe setup and near-misses
python3 -I "$CHECK" "$FIX/clean" --json > "$TMP/c.json"
assert "clean: zero findings" "$TMP/c.json" "d['findings'] == [] and d['suppressed'] == []"
assert "clean: release setup was seen" "$TMP/c.json" "d['stats']['flavors'] == {'android': ['dev', 'prod'], 'ios': ['dev', 'prod'], 'entrypoints': ['dev', 'prod']} and d['stats']['app_kind'] == 'app' and len(d['stats']['ci_files']) == 2"
python3 -I "$CHECK" "$FIX/clean" > "$TMP/c.txt"
grep -q '^  no release findings$' "$TMP/c.txt" && pass "clean: text says no findings" || bad "clean: text says no findings"
cp -R "$FIX/clean" "$TMP/clean_keys"
printf 'FAKE PLACEHOLDER\n' > "$TMP/clean_keys/android/app/upload-keystore.jks"
printf 'storeFile=upload-keystore.jks\n' > "$TMP/clean_keys/android/key.properties"
printf 'FAKE PLACEHOLDER\n' > "$TMP/clean_keys/android/debug.keystore"
python3 -I "$CHECK" "$TMP/clean_keys" --json > "$TMP/ck.json"
assert "clean: ignored local keystore, key.properties and the debug.keystore are fine" "$TMP/ck.json" "d['findings'] == []"
printf 'FAKE PLACEHOLDER\n' > "$TMP/clean_keys/ios/dist.p12"
python3 -I "$CHECK" "$TMP/clean_keys" --json > "$TMP/ck2.json"
assert "clean: an unignored .p12 still fires (TP REL-002)" "$TMP/ck2.json" "[(f['id'], f['file'], f['severity']) for f in d['findings']] == [('REL-002', 'ios/dist.p12', 'high')]"

# --- suppression
python3 -I "$CHECK" "$FIX/suppressed" --json > "$TMP/s.json"
assert "suppress: unsuppressed hit still reported" "$TMP/s.json" "[(f['id'], f['file'], f['line']) for f in d['findings']] == [('REL-011', '.github/workflows/ci.yml', 11)]"
assert "suppress: // line-above, // file and # line-above honoured" "$TMP/s.json" "sorted((s['id'], s['file']) for s in d['suppressed']) == [('REL-001', 'android/app/build.gradle'), ('REL-006', 'lib/features/banner/presentation/view/banner_view.dart'), ('REL-011', '.github/workflows/ci.yml')]"
assert "suppress: reasons kept" "$TMP/s.json" "all(s['reason'] and s['reason'] != '(no reason given)' for s in d['suppressed'])"
python3 -I "$CHECK" "$FIX/suppressed" | grep -q '^  suppressed: 3 (see --json)$' && pass "suppress: text summary line" || bad "suppress: text summary line"

# --- fallback without the flutter-architecture sibling
mkdir -p "$TMP/lonely/scripts"
cp "$CHECK" "$TMP/lonely/scripts/check_release.py"
python3 -I "$TMP/lonely/scripts/check_release.py" "$FIX/violations" --json > "$TMP/fb.json"
assert "fallback: says it used path-based classification" "$TMP/fb.json" "d['classification'].startswith('path-based fallback')"
assert "fallback: every rule still fires" "$TMP/fb.json" "ids == {'REL-%03d' % i for i in range(1, 13)}"
assert "fallback: the same REL-006 files" "$TMP/fb.json" "len(of('REL-006')) == 2"
assert "fallback: profile detected from pubspec/folders" "$TMP/fb.json" "d['profile']['source'].startswith('fallback')"
python3 -I "$TMP/lonely/scripts/check_release.py" "$FIX/violations" | grep -q '^  classification: path-based fallback' && pass "fallback: text output says so" || bad "fallback: text output says so"
python3 -I "$TMP/lonely/scripts/check_release.py" "$FIX/clean" --json > "$TMP/fbc.json"
assert "fallback: clean fixture still zero" "$TMP/fbc.json" "d['findings'] == []"

# --- --profile override
python3 -I "$CHECK" "$FIX/violations" --json --profile bloc > "$TMP/p.json"
assert "--profile bloc: RepositoryProvider placement in REL-005/006 notes" "$TMP/p.json" "d['profile']['presentation'] == 'bloc' and d['profile']['source'].startswith('declared') and all('RepositoryProvider' in f['note'] and 'ProviderScope' not in f['note'] for f in of('REL-005') + of('REL-006'))"
python3 -I "$CHECK" "$FIX/violations" --json --profile getx > "$TMP/p2.json"
assert "--profile getx: Get.put in the binding" "$TMP/p2.json" "all('Get.put' in f['note'] for f in of('REL-005'))"

# --- calibration regressions (references/rules.md, Calibration)
python3 -I "$CHECK" "$FIX/calib_samples" --json > "$TMP/cs.json"
assert "calib_samples: changed applicationId alone is no release intent, REL-001 graded info" "$TMP/cs.json" "d['stats']['app_kind'] == 'sample' and [f['severity'] for f in of('REL-001')] == ['info'] and 'sample app' in of('REL-001')[0]['note']"
assert "calib_samples: store-readiness rules stay info (REL-003, REL-008 are still reported)" "$TMP/cs.json" "of('REL-003', 'info') and of('REL-008', 'info') and not [f for f in d['findings'] if f['severity'] != 'info']"
python3 -I "$CHECK" "$FIX/calib_samples/examples/signed_demo" --json > "$TMP/cse.json"
assert "calib_samples: an app inside examples/ is a sample even with a signing config" "$TMP/cse.json" "'inside an examples' in of('REL-001')[0]['note'] and not [f for f in d['findings'] if f['severity'] != 'info']"
assert "calib_samples: the same debug-signed release with release intent is high (TP)" "$TMP/v.json" "of('REL-001', 'high')"
python3 -I "$CHECK" "$FIX/calib_news" --json > "$TMP/cn.json"
assert "calib_news: real flavors in Kotlin DSL, schemes and lib/main/ entrypoints match" "$TMP/cn.json" "d['findings'] == [] and d['stats']['flavors']['android'] == ['development', 'production'] and d['stats']['flavors']['entrypoints'] == ['development', 'production']"
assert "calib_news: debug buildType using the debug key is not REL-001" "$TMP/cn.json" "'REL-001' not in ids"
python3 -I "$CHECK" "$FIX/calib_hiddify" --json > "$TMP/ch.json"
assert "calib_hiddify: if/else fallback to the debug key is info, not high" "$TMP/ch.json" "[f['severity'] for f in of('REL-001')] == ['info'] and 'falls back' in of('REL-001')[0]['note']"
assert "calib_hiddify: a DSN disabled in debug builds is not REL-005" "$TMP/ch.json" "not at('lib/core/telemetry/reporter.dart', 14, 'REL-005')"
assert "calib_hiddify: dev/prod API URLs by kDebugMode still fire (TP REL-005)" "$TMP/ch.json" "at('lib/core/telemetry/reporter.dart', 16, 'REL-005')"
assert "calib_hiddify: extension scheme and main_prod.dart without flavors are not REL-004" "$TMP/ch.json" "'REL-004' not in ids and d['stats']['flavors']['ios'] == []"
python3 -I "$CHECK" "$FIX/calib_immich/app" --json > "$TMP/ci.json"
assert "calib_immich: ternary fallback to the debug key is info" "$TMP/ci.json" "[f['severity'] for f in of('REL-001')] == ['info']"
assert "calib_immich: main_timeline.page.dart is not a flavor entrypoint" "$TMP/ci.json" "d['stats']['flavors']['entrypoints'] == []"
mkdir -p "$TMP/mono"
cp -R "$FIX/calib_immich/." "$TMP/mono/"
mkdir -p "$TMP/mono/.git"
python3 -I "$CHECK" "$TMP/mono/app" --json > "$TMP/cim.json"
assert "calib_immich: the monorepo workflow that mentions app/ is read, with a ../ path" "$TMP/cim.json" "d['stats']['ci_files'] == ['../.github/workflows/mobile.yml']"
assert "calib_immich: keystore left on a non-hosted runner fires low (TP REL-012)" "$TMP/cim.json" "[(f['file'], f['line'], f['severity']) for f in of('REL-012')] == [('../.github/workflows/mobile.yml', 17, 'low')]"
assert "calib_immich: the same decode on ubuntu-24.04 and an apk-only upload are not REL-012" "$TMP/cim.json" "len(of('REL-012')) == 1"
python3 -I "$CHECK" "$TMP/mono/app" --json --files ../.github/workflows/mobile.yml > "$TMP/cimf.json"
assert "calib_immich: --files takes the ../ workflow path" "$TMP/cimf.json" "ids == {'REL-012'}"
python3 -I "$CHECK" "$FIX/calib_lichess" --json > "$TMP/cl.json"
assert "calib_lichess: numeric kDebugMode ternaries are not REL-005" "$TMP/cl.json" "[f['line'] for f in of('REL-005')] == [8]"
assert "calib_lichess: wss/ws hosts by kReleaseMode still fire (TP REL-005)" "$TMP/cl.json" "at('lib/src/engine/search.dart', 8, 'REL-005')"
assert "calib_lichess: localized Runner scheme and widget extension are not flavors" "$TMP/cl.json" "d['stats']['flavors']['ios'] == [] and 'REL-004' not in ids"
assert "calib_lichess: key.properties written on a hosted runner, aab-only upload, is fine" "$TMP/cl.json" "'REL-012' not in ids and 'REL-011' not in ids"

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
python3 -I "$CHECK" "$TMP/nolib" | grep -q '^  no release findings$' && pass "no lib/: text report" || bad "no lib/: text report"
mkdir -p "$TMP/pkg/lib"; printf 'name: pkg\n' > "$TMP/pkg/pubspec.yaml"; printf 'const kDebugX = 1;\n' > "$TMP/pkg/lib/pkg.dart"
python3 -I "$CHECK" "$TMP/pkg" --json > "$TMP/pkg.json"
assert "pure Dart package: platform rules skipped and said so" "$TMP/pkg.json" "d['stats']['app_kind'] == 'package' and d['stats']['platform_rules'].startswith('skipped') and d['findings'] == []"

[ $fail = 0 ] && echo "ALL flutter-release TESTS PASSED" || echo "flutter-release: SOME TESTS FAILED"
exit $fail
