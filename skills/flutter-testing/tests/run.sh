#!/usr/bin/env bash
# Regression tests for scripts/test_gaps.py.
# Needs bash 3.2+ and python3 >= 3.8 (stdlib only). No Flutter/Dart SDK, no pub get.
# Prints PASS/FAIL lines; exits 1 on any failure.
set -u

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPT="$HERE/../scripts/test_gaps.py"
FIX="$HERE/fixtures"
TMP="$(mktemp -d "${TMPDIR:-/tmp}/test-gaps-tests.XXXXXX")"
trap 'rm -rf "$TMP"' EXIT
PASS=0
FAIL=0

pass() { PASS=$((PASS + 1)); echo "PASS $1"; }
fail() { FAIL=$((FAIL + 1)); echo "FAIL $1"; if [ -n "${2:-}" ]; then echo "     $2"; fi; }
expect() { # label got want
  if [ "$2" == "$3" ]; then pass "$1"; else fail "$1" "want [$3] got [$2]"; fi
}

# run_json <name> <script> <project-dir> [args...]  ->  $TMP/<name>.json
run_json() {
  local name="$1" script="$2" dir="$3"
  shift 3
  python3 -I "$script" "$dir" --json "$@" > "$TMP/$name.json" 2> "$TMP/$name.err"
  local rc=$?
  if [ $rc -ne 0 ]; then fail "$name: exit code" "exit $rc: $(head -c 300 "$TMP/$name.err")"; fi
}

# q <name> <query>
#   gaps             ranked gap files, comma-separated basenames
#   gap_ids          ranked gap ids
#   method:<file>    mapping methods of a unit (basename), comma-separated
#   tested:<file>    true|false
#   note:<file>      the unit's note
#   count:<id>       number of smells with that id
#   lines:<id>       smell lines for that id, comma-separated
#   files:<id>       smell file basenames for that id
#   classifier | profile | coverage:<role> | keys
q() {
  python3 -I - "$TMP/$1.json" "$2" <<'PY'
import json, sys
r = json.load(open(sys.argv[1]))
qq = sys.argv[2]
base = lambda p: p.rsplit('/', 1)[-1]
units = {base(u['file']): u for u in r['units']}
if qq == 'gaps':
    print(','.join(base(g['file']) for g in r['gaps']))
elif qq == 'gap_ids':
    print(','.join(g['id'] for g in r['gaps']))
elif qq.startswith('method:'):
    print(','.join(t['method'] for t in units[qq[7:]]['tests']))
elif qq.startswith('tested:'):
    print(str(units[qq[7:]]['tested']).lower())
elif qq.startswith('note:'):
    print(units[qq[5:]]['note'])
elif qq.startswith('count:'):
    print(sum(1 for s in r['smells'] if s['id'] == qq[6:]))
elif qq.startswith('lines:'):
    print(','.join(str(s['line']) for s in r['smells'] if s['id'] == qq[6:]))
elif qq.startswith('files:'):
    print(','.join(sorted({base(s['file']) for s in r['smells'] if s['id'] == qq[6:]})))
elif qq.startswith('role:'):
    print(units[qq[5:]]['role'] if qq[5:] in units else 'not-a-unit')
elif qq.startswith('classes:'):
    print(','.join(units[qq[8:]]['classes']))
elif qq.startswith('skipped:'):
    print(','.join(x['reason'] for x in r['stats']['skipped'] if base(x['file']) == qq[8:]))
elif qq.startswith('severity:'):
    print(','.join(g['severity'] for g in r['gaps'] if base(g['file']) == qq[9:]))
elif qq == 'path_packages':
    print(','.join('%s:%d' % (x['path'], x['test_files']) for x in r['stats']['path_packages']))
elif qq.startswith('evidence:'):
    print('|'.join(s['evidence'] for s in r['smells'] if s['id'] == qq[9:]))
elif qq == 'classifier':
    print(r['profile']['classifier'])
elif qq == 'profile':
    print(r['profile']['presentation'])
elif qq.startswith('coverage:'):
    v = r['stats']['coverage_by_role'][qq[9:]]
    print('%d/%d %s' % (v['tested'], v['units'], v['pct']))
elif qq == 'keys':
    ok = []
    ok.append(set(r) == {'schema', 'profile', 'units', 'gaps', 'smells', 'stats'})
    ok.append(r['schema'] == 'flutter-pro-skills/test-gaps@1')
    ok.append({'presentation', 'clean_architecture', 'confidence', 'signals', 'classifier', 'classifier_note'} <= set(r['profile']))
    ok.append(all({'file', 'role', 'layer', 'feature', 'classes', 'lines', 'complexity', 'tested', 'tests', 'note'} <= set(u)
                  and all(t['method'] in ('mirror', 'name', 'import') for t in u['tests']) for u in r['units']))
    ok.append(all({'rank', 'id', 'severity', 'tier', 'file', 'role', 'lines', 'complexity', 'indirect', 'message', 'note'} <= set(g)
                  and g['id'].startswith('TEST-untested-') and g['severity'] in ('medium', 'low', 'info') for g in r['gaps']))
    ok.append([g['rank'] for g in r['gaps']] == list(range(1, len(r['gaps']) + 1)))
    ok.append(all(set(s) == {'id', 'severity', 'file', 'line', 'evidence', 'message'} and isinstance(s['line'], int)
                  and s['id'].startswith('TEST-') for s in r['smells']))
    st = r['stats']
    ok.append({'units', 'tested', 'coverage_pct', 'coverage_by_role', 'test_files', 'tests', 'mapping', 'smells'} <= set(st))
    ok.append(all(set(v) == {'units', 'tested', 'pct'} for v in st['coverage_by_role'].values()))
    ok.append(bool(r['gaps']) and bool(r['smells']))
    print('ok' if all(ok) else 'bad:' + ''.join('1' if o else '0' for o in ok))
PY
}

SNAP_BEFORE="$(cd "$FIX" && find . -type f | sort | xargs cksum)"

# ---------------------------------------------------------------- mvn_app (arch_check classifier)
MVN_GAPS="checkout_usecase.dart,cart_usecase.dart,cart_notifier.dart,movie_source.dart,cart_api.dart,cart_view.dart,cart_badge.dart"
run_json mvn "$SCRIPT" "$FIX/mvn_app"
expect "mvn: JSON keys and shapes" "$(q mvn keys)" ok
expect "mvn: profile" "$(q mvn profile)" mvn
if [ -f "$HERE/../../flutter-architecture/scripts/arch_check.py" ]; then
  expect "mvn: classifier uses arch_check when installed" "$(q mvn classifier)" arch_check
fi
expect "mvn: gap ranking (repo/usecase > logic > source > view > widget; trivial and indirect last in tier)" "$(q mvn gaps)" "$MVN_GAPS"
expect "mvn: gap ids follow the tiers" "$(q mvn gap_ids)" \
  "TEST-untested-usecase,TEST-untested-usecase,TEST-untested-logic,TEST-untested-source,TEST-untested-source,TEST-untested-view,TEST-untested-widget"
expect "mvn: mirror path maps the repository impl" "$(q mvn method:movie_repository_impl.dart)" mirror
expect "mvn: name match maps the notifier (test/notifiers/movie_notifier_test.dart)" "$(q mvn method:movie_notifier.dart)" name
expect "mvn: import + construct maps the use case" "$(q mvn method:movie_usecase.dart)" import
expect "mvn: import + construct maps the view" "$(q mvn method:movie_view.dart)" import
expect "mvn: find.byType maps a widget" "$(q mvn method:movie_list.dart)" import
expect "mvn: provider override alone does not count as a test" "$(q mvn tested:movie_source.dart)" false
expect "mvn: override note on the source" "$(q mvn note:movie_source.dart)" "its provider is overridden with a fake in 2 test file(s)"
expect "mvn: pass-through note on the use case" "$(q mvn note:cart_usecase.dart)" \
  "pass-through (no branches): a logic test that runs the real use case over a fake repository covers it"
expect "mvn: import + call maps a top-level function with named params" "$(q mvn method:cart_rules.dart)" import
expect "mvn: coverage by role (usecase)" "$(q mvn coverage:usecase)" "2/4 50.0"
expect "mvn: coverage by role (repository-impl)" "$(q mvn coverage:repository-impl)" "2/2 100.0"

# smells
expect "mvn: TEST-no-assertion (plain, string-only, commented-out)" "$(q mvn lines:TEST-no-assertion)" "22,27,31"
expect "mvn: helpers, bloc_test expect: and local expect helpers are assertions" "$(q mvn files:TEST-no-assertion)" "smelly_test.dart"
expect "mvn: TEST-real-delay (sleep, wall-clock delayed, runAsync)" "$(q mvn lines:TEST-real-delay)" "60,65,70"
expect "mvn: TEST-real-network (Dio(), http.Client(); adapter and real/ exempt)" "$(q mvn lines:TEST-real-network)" "98,103"
expect "mvn: TEST-skip-no-reason (skip: true only; reasons and blocTest skip: 1 are fine)" "$(q mvn lines:TEST-skip-no-reason)" "111"
expect "mvn: TEST-giant-file" "$(q mvn files:TEST-giant-file)" "giant_test.dart"
expect "mvn: TEST-mock-of-sut" "$(q mvn files:TEST-mock-of-sut)" "cart_repository_impl_test.dart"
expect "mvn: TEST-preview-only" "$(q mvn lines:TEST-preview-only)" "118"

# text output
python3 -I "$SCRIPT" "$FIX/mvn_app" --max 1 > "$TMP/mvn.txt" 2>&1
expect "mvn text: section headers" "$(grep -E '^== ' "$TMP/mvn.txt" | tr '\n' '|')" "== TEST GAPS|== TEST SMELLS|"
expect "mvn text: group line format" \
  "$(grep -cE '^  \[TEST-[a-z-]+\] \((high|medium|low|info)\) x[0-9]+ — ' "$TMP/mvn.txt" | tr -d ' ')" 12
expect "mvn text: --max truncates (usecase, source, real-network groups)" \
  "$(grep -c '^      \.\.\. 1 more$' "$TMP/mvn.txt" | tr -d ' ')" 3
expect "mvn text: first gap ranked #1" "$(grep -m1 -oE '#1 [^ ]+' "$TMP/mvn.txt")" "#1 lib/features/cart/domain/usecases/checkout_usecase.dart"

# ---------------------------------------------------------------- mvvm_app
run_json mvvm "$SCRIPT" "$FIX/mvvm_app"
expect "mvvm: profile" "$(q mvvm profile)" mvvm
# (fixture service renamed from analytics_service: analytics/logger services are core, not data, under arch_check K3 A15)
expect "mvvm: gap ranking (service before view)" "$(q mvvm gaps)" "history_service.dart,todo_screen.dart"
expect "mvvm: mirror under test/unit/" "$(q mvvm method:todo_view_model.dart)" mirror
expect "mvvm: import maps TodoRepositoryRemote" "$(q mvvm method:todo_repository.dart)" import
expect "mvvm: @GenerateMocks of the SUT" "$(q mvvm count:TEST-mock-of-sut)" 1
expect "mvvm: no false smells" "$(q mvvm count:TEST-no-assertion)$(q mvvm count:TEST-real-network)" "00"

# ---------------------------------------------------------------- fallback (no flutter-architecture sibling)
mkdir -p "$TMP/solo/skills/flutter-testing/scripts"
cp "$SCRIPT" "$TMP/solo/skills/flutter-testing/scripts/test_gaps.py"
cp -R "$FIX/mvn_app" "$TMP/solo/mvn_app"
cp -R "$FIX/mvvm_app" "$TMP/solo/mvvm_app"
SOLO="$TMP/solo/skills/flutter-testing/scripts/test_gaps.py"
run_json fb_mvn "$SOLO" "$TMP/solo/mvn_app"
expect "fallback: classifier" "$(q fb_mvn classifier)" fallback
expect "fallback: mvn profile from pubspec + folders" "$(q fb_mvn profile)" mvn
expect "fallback: same gap ranking" "$(q fb_mvn gaps)" "$MVN_GAPS"
expect "fallback: same mappings" "$(q fb_mvn method:movie_notifier.dart)/$(q fb_mvn method:movie_usecase.dart)" "name/import"
expect "fallback: JSON keys" "$(q fb_mvn keys)" ok
python3 -I "$SOLO" "$TMP/solo/mvn_app" > "$TMP/fb.txt" 2>&1
expect "fallback: text says so" "$(grep -c 'classifier: fallback (flutter-architecture skill not installed' "$TMP/fb.txt" | tr -d ' ')" 1
run_json fb_mvvm "$SOLO" "$TMP/solo/mvvm_app"
expect "fallback: mvvm gap ranking" "$(q fb_mvvm gaps)" "history_service.dart,todo_screen.dart"
expect "fallback: --profile wins" "$(python3 -I "$SOLO" "$TMP/solo/mvvm_app" --json --profile bloc | python3 -I -c 'import json,sys; print(json.load(sys.stdin)["profile"]["presentation"])')" bloc

# ---------------------------------------------------------------- calib_app (calibration K1-K3 regressions)
# Each block names the report item; minimal repros come from the K1-K3 calibration reports.
calib_checks() { # <name> <label-prefix>
  local n="$1" p="$2"
  expect "$p K1-T1: login_widget_test.dart maps lib/screens/login.dart by name" "$(q $n method:login.dart)" name
  expect "$p K1-T2: a file of exception classes is not a unit" "$(q $n skipped:sync_error.dart)" "exception, value or contract types only"
  expect "$p K1-T2 guard: a widget named *Error is still a unit" "$(q $n role:weather_error.dart)" widget
  expect "$p K1-T2 guard: a class generic over an *Error enum is still a unit" "$(q $n role:quota_service.dart)" service
  expect "$p K1-T3: a *Dev repository stub is not a unit" "$(q $n skipped:auth_repository_dev.dart)" "dev stub or fake"
  expect "$p K1-T3: a *Factory is not a unit" "$(q $n role:repository_factory.dart)" not-a-unit
  expect "$p K1-T3: a thin delegating repository impl is reported low" "$(q $n severity:profile_repository_impl.dart)" low
  expect "$p K1-T3: thin note" "$(q $n note:profile_repository_impl.dart | cut -c1-16)" "thin delegation "
  expect "$p K2-T1: abstract UseCase + NoParams is not a unit" "$(q $n skipped:usecase.dart)" "exception, value or contract types only"
  expect "$p s18/K1 FN: a ChangeNotifier manager is logic and maps by mirror" "$(q $n role:habits_manager.dart)/$(q $n method:habits_manager.dart)" logic/mirror
  expect "$p s18: a ChangeNotifier under models/ is logic" "$(q $n role:cart.dart)" logic
  expect "$p s18/K3 FN: a StateNotifier in providers/*.provider.dart is logic" "$(q $n role:album.provider.dart)" logic
  expect "$p K3 A6: a provider-only *_repository_provider.dart is not a unit" "$(q $n role:user_repository_provider.dart)" not-a-unit
  expect "$p K3 A10: a *_controller.dart holding only widgets is a widget" "$(q $n role:animation_controller.dart)" widget
  expect "$p K3-T4: lib/src/model/x.dart maps test/model/x_test.dart by mirror" "$(q $n method:game_service.dart)" mirror
  expect "$p Dart 3.13 primary constructor: class name read, import mapping works" "$(q $n classes:board.dart)/$(q $n method:board.dart)" Board/import
  expect "$p K3-T1: migrateAndValidate / validateX count as assertions; a no-op test still fires" "$(q $n evidence:TEST-no-assertion)" "test('initialize is a no-op')"
  expect "$p K3-T2: zero and <=1 ms delays exempt; a 2 ms wait still fires" "$(q $n lines:TEST-real-delay)" 14
  expect "$p K1 FN: tests-the-mock (stub then call the mock, also inside expect); a real SUT over the mock is fine" "$(q $n lines:TEST-tests-the-mock)" "19,36"
  expect "$p K2 P4: path packages are listed as not scanned" "$(q $n path_packages)" "packages/foo_repository:1"
  expect "$p JSON keys" "$(q $n keys)" ok
}
run_json calib "$SCRIPT" "$FIX/calib_app"
calib_checks calib "calib:"
python3 -I "$SCRIPT" "$FIX/calib_app" > "$TMP/calib.txt" 2>&1
expect "calib text: not-units and path-packages header lines" \
  "$(grep -cE '^  (not units: 3 \(|path packages \(not scanned; run test_gaps.py on each\): packages/foo_repository \(1 test files\))' "$TMP/calib.txt" | tr -d ' ')" 2
cp -R "$FIX/calib_app" "$TMP/solo/calib_app"
run_json fb_calib "$SOLO" "$TMP/solo/calib_app"
expect "fallback calib: classifier" "$(q fb_calib classifier)" fallback
calib_checks fb_calib "fallback calib:"
expect "fallback calib: same gap ranking as arch_check" "$(q fb_calib gaps)" "$(q calib gaps)"

# ---------------------------------------------------------------- usage errors and read-only
mkdir -p "$TMP/empty"
python3 -I "$SCRIPT" "$TMP/empty" > /dev/null 2>&1
expect "usage: no pubspec.yaml exits 2" "$?" 2
python3 -I "$SCRIPT" "$FIX/mvn_app" --bogus > /dev/null 2>&1
expect "usage: unknown flag exits 2" "$?" 2
python3 -I "$SCRIPT" "$FIX/mvn_app" --profile nope > /dev/null 2>&1
expect "usage: bad --profile exits 2" "$?" 2
mkdir -p "$TMP/nolib" && printf 'name: nolib\n' > "$TMP/nolib/pubspec.yaml"
python3 -I "$SCRIPT" "$TMP/nolib" > /dev/null 2>&1
expect "no lib/: report with exit 0" "$?" 0
SNAP_AFTER="$(cd "$FIX" && find . -type f | sort | xargs cksum)"
expect "read-only: fixtures unchanged" "$([ "$SNAP_BEFORE" == "$SNAP_AFTER" ] && echo same || echo changed)" same

echo
echo "flutter-testing: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ] || exit 1
