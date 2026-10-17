#!/usr/bin/env bash
# Tests for flutter-error-handling/scripts/check_errors.py.
# No Flutter SDK or pub get needed: the checker is static. bash 3.2 compatible.
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL="$(cd "$HERE/.." && pwd)"
CHECK="$SKILL/scripts/check_errors.py"
FIX="$HERE/fixtures"
TMP="$(mktemp -d "${TMPDIR:-/tmp}/errcheck.XXXXXX")"
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
  pass "check_errors.py parses as Python 3.8"
else
  bad "check_errors.py parses as Python 3.8"
fi

# --- violations fixture: every rule fires
before="$(checksum "$FIX/violations")"
python3 -I "$CHECK" "$FIX/violations" --json > "$TMP/v.json"; rc=$?
[ $rc = 0 ] && pass "violations: exit 0 with findings" || bad "violations: exit 0 with findings (got $rc)"
after="$(checksum "$FIX/violations")"
[ "$before" = "$after" ] && pass "read-only: fixture unchanged" || bad "read-only: fixture unchanged"
for n in 001 002 003 004 005 006 007 008 009 010 011 012 013; do
  assert "violations: ERR-$n triggered" "$TMP/v.json" "'ERR-$n' in ids"
done
D=lib/features/movie
assert "ERR-001 high for an undocumented empty catch"   "$TMP/v.json" "at('$D/data/sources/movie_api.dart', 18, 'ERR-001')[0]['severity'] == 'high'"
assert "ERR-001 low for undocumented cleanup-only try"  "$TMP/v.json" "at('$D/data/sources/movie_cache.dart', 18, 'ERR-001')[0]['severity'] == 'low'"
assert "ERR-001 info for documented cleanup"            "$TMP/v.json" "at('$D/data/sources/movie_cache.dart', 13, 'ERR-001')[0]['severity'] == 'info'"
assert "ERR-001 high for catchError((_) {})"             "$TMP/v.json" "at('$D/presentation/view/movie_view.dart', 21, 'ERR-001')[0]['severity'] == 'high'"
assert "ERR-002 medium when error value is dropped"     "$TMP/v.json" "at('$D/data/sources/movie_api.dart', 34, 'ERR-002')[0]['severity'] == 'medium'"
assert "ERR-002 info when documented"                   "$TMP/v.json" "at('$D/data/sources/movie_api.dart', 24, 'ERR-002')[0]['severity'] == 'info'"
assert "ERR-008 medium in a view, low in a notifier"    "$TMP/v.json" "at('$D/presentation/view/movie_view.dart', 19, 'ERR-008')[0]['severity'] == 'medium' and at('$D/presentation/notifier/movie_notifier.dart', 27, 'ERR-008')[0]['severity'] == 'low'"
assert "ERR-006 high for throw, medium for on-clause"   "$TMP/v.json" "at('$D/domain/usecases/get_trending.dart', 15, 'ERR-006')[0]['severity'] == 'high' and at('$D/domain/usecases/get_trending.dart', 14, 'ERR-006')[0]['severity'] == 'medium'"
assert "ERR-004 reported once per repository"           "$TMP/v.json" "len([f for f in d['findings'] if f['id'] == 'ERR-004']) == 1"
assert "ERR-009 mix reported on the contract only"      "$TMP/v.json" "[f['file'] for f in d['findings'] if f['id'] == 'ERR-009' and f['severity'] == 'low'] == ['$D/domain/repositories/movie_repository.dart']"
assert "ERR-012 medium when a reporter dep is unwired"  "$TMP/v.json" "[f['severity'] for f in d['findings'] if f['id'] == 'ERR-012'] == ['medium']"
assert "ERR-010 note carries the profile's fix (mvn)"   "$TMP/v.json" "[f for f in d['findings'] if f['id'] == 'ERR-010'][0]['note'].startswith('MVN:')"
assert "uses arch_check files[] when installed"         "$TMP/v.json" "d['classification'] == 'arch_check files[]' or d['classification'].startswith('path-based fallback (flutter-architecture')"

# --- JSON contract
assert "JSON: schema and top-level keys" "$TMP/v.json" "d['schema'] == 'flutter-pro-skills/error-check@1' and set(d) >= {'schema','root','package','profile','classification','stats','findings','suppressed'}"
assert "JSON: finding keys"              "$TMP/v.json" "all(set(f) == {'id','name','severity','file','line','evidence','message','note'} for f in d['findings'])"
assert "JSON: profile and stats keys"    "$TMP/v.json" "set(d['profile']) >= {'presentation','source'} and set(d['stats']) >= {'files','catch_clauses','throw_statements','result_returning_methods','error_style','global_handlers'}"
assert "JSON: severities are known"      "$TMP/v.json" "all(f['severity'] in ('high','medium','low','info') for f in d['findings'])"

# --- text output (arch_check style)
python3 -I "$CHECK" "$FIX/violations" --max 1 > "$TMP/v.txt"
head -1 "$TMP/v.txt" | grep -q '^== ERROR HANDLING$' && pass "text: header" || bad "text: header"
grep -Eq '^  \[ERR-001\] swallowed-catch \(high\) x[0-9]+ — ' "$TMP/v.txt" && pass "text: group line format" || bad "text: group line format"
grep -Eq '^      lib/[^ ]+\.dart:[0-9]+  ' "$TMP/v.txt" && pass "text: location lines" || bad "text: location lines"
grep -Eq '^      \.\.\. [0-9]+ more$' "$TMP/v.txt" && pass "text: --max collapses extra locations" || bad "text: --max collapses extra locations"

# --- --files (file list and comma list)
echo "lib/features/movie/data/sources/movie_api.dart" > "$TMP/files.txt"
python3 -I "$CHECK" "$FIX/violations" --json --files "$TMP/files.txt" > "$TMP/f.json"
assert "--files: only listed files reported" "$TMP/f.json" "d['findings'] and all(f['file'] == 'lib/features/movie/data/sources/movie_api.dart' for f in d['findings'])"
assert "--files: cross-file rules still see the whole project" "$TMP/f.json" "'ERR-002' in ids and 'ERR-004' not in ids"
python3 -I "$CHECK" "$FIX/violations" --json --files "lib/main.dart,lib/features/movie/data/repositories/movie_repository_impl.dart" > "$TMP/f2.json"
assert "--files: comma-separated list" "$TMP/f2.json" "ids >= {'ERR-012','ERR-013','ERR-004','ERR-007'} and all(f['file'] in ('lib/main.dart','lib/features/movie/data/repositories/movie_repository_impl.dart') for f in d['findings'])"

# --- bloc fixture
python3 -I "$CHECK" "$FIX/bloc_violations" --json > "$TMP/b.json"
assert "bloc: ERR-010 for Bloc handler and Cubit status enum" "$TMP/b.json" "sorted((f['file'].split('/')[-1], f['id']) for f in d['findings']) == [('todo_bloc.dart','ERR-010'), ('todo_cubit.dart','ERR-010')]"
assert "bloc: wired global handlers are not reported" "$TMP/b.json" "'ERR-012' not in ids"
assert "bloc: fix hint follows the bloc profile" "$TMP/b.json" "all(f['note'].startswith('Bloc:') for f in d['findings'])"

# --- clean fixture
python3 -I "$CHECK" "$FIX/clean" --json > "$TMP/c.json"
assert "clean: zero findings" "$TMP/c.json" "d['findings'] == [] and d['suppressed'] == []"
assert "clean: Result style detected" "$TMP/c.json" "d['stats']['error_style'] == 'result'"
python3 -I "$CHECK" "$FIX/clean" > "$TMP/c.txt"
grep -q 'no error-handling findings' "$TMP/c.txt" && pass "clean: text says no findings" || bad "clean: text says no findings"

# --- suppression
python3 -I "$CHECK" "$FIX/suppressed" --json > "$TMP/s.json"
assert "suppress: unsuppressed hit still reported" "$TMP/s.json" "[(f['id'], f['file'], f['line']) for f in d['findings']] == [('ERR-005', 'lib/src/line_ignored.dart', 15)]"
assert "suppress: line, in-block and file comments honoured" "$TMP/s.json" "sorted((s['id'], s['file']) for s in d['suppressed']) == [('ERR-001','lib/src/line_ignored.dart'), ('ERR-001','lib/src/line_ignored.dart'), ('ERR-005','lib/src/file_ignored.dart'), ('ERR-005','lib/src/file_ignored.dart')]"
assert "suppress: reasons kept" "$TMP/s.json" "all(s['reason'] and s['reason'] != '(no reason given)' for s in d['suppressed'])"
assert "suppress: pure Dart package skips ERR-012" "$TMP/s.json" "'ERR-012' not in ids"
python3 -I "$CHECK" "$FIX/suppressed" | grep -q '^  suppressed: 4 (see --json)$' && pass "suppress: text summary line" || bad "suppress: text summary line"

# --- fallback without the flutter-architecture sibling
mkdir -p "$TMP/lonely/scripts"
cp "$CHECK" "$TMP/lonely/scripts/check_errors.py"
python3 -I "$TMP/lonely/scripts/check_errors.py" "$FIX/violations" --json > "$TMP/fb.json"
assert "fallback: says it used path-based classification" "$TMP/fb.json" "d['classification'].startswith('path-based fallback')"
assert "fallback: every rule still fires" "$TMP/fb.json" "ids == {'ERR-%03d' % i for i in range(1, 15)}"
assert "fallback: profile detected from pubspec/folders" "$TMP/fb.json" "d['profile']['presentation'] == 'mvn' and d['profile']['source'].startswith('fallback')"
python3 -I "$TMP/lonely/scripts/check_errors.py" "$FIX/violations" | grep -q '^  classification: path-based fallback' && pass "fallback: text output says so" || bad "fallback: text output says so"
python3 -I "$TMP/lonely/scripts/check_errors.py" "$FIX/clean" --json > "$TMP/fbc.json"
assert "fallback: clean fixture still zero" "$TMP/fbc.json" "d['findings'] == []"

python3 -I "$TMP/lonely/scripts/check_errors.py" "$FIX/calib_mvvm" --json > "$TMP/fbm.json"
assert "fallback: Command/typedef Result clean, State-class ERR-010 still found" "$TMP/fbm.json" "not [f for f in d['findings'] if f['id'] == 'ERR-010' and f['file'] in ('lib/utils/command.dart',) or (f['id'] == 'ERR-010' and f['line'] in (28, 38))] and at('lib/ui/sync/widgets/sync_screen.dart', 18, 'ERR-010')"

# --- calibration regressions (phase 3: K1 MVVM/Provider, K2 Bloc/Clean, K3 Riverpod/GetX/setState)
M=lib/ui/home/view_models/home_viewmodel.dart
python3 -I "$CHECK" "$FIX/calib_mvvm" --json > "$TMP/m.json"
assert "K1-E1: Command with try/finally reset is not ERR-010"           "$TMP/m.json" "not [f for f in d['findings'] if f['file'] == 'lib/utils/command.dart']"
assert "K1-E1: awaited Result via the repository contract: no ERR-010"   "$TMP/m.json" "not at('$M', 28, 'ERR-010')"
assert "K1-E1: awaited Result via a typedef'd field: no ERR-010"         "$TMP/m.json" "not at('$M', 38, 'ERR-010')"
assert "K1-E1 TP: unguarded throwing await still ERR-010 high"           "$TMP/m.json" "at('$M', 48, 'ERR-010')[0]['severity'] == 'high'"
assert "typedef: Attempt<T> = Future<Result<T>> counts as Result"        "$TMP/m.json" "d['stats']['result_returning_methods'] == 2 and at('lib/data/repositories/habit_repository.dart', 54, 'ERR-009')"
assert "K1-E2: collection-only try is not ERR-007, ERR-001 low"          "$TMP/m.json" "not at('lib/data/repositories/habit_repository.dart', 34, 'ERR-007') and at('lib/data/repositories/habit_repository.dart', 34, 'ERR-001')[0]['severity'] == 'low' and 'firstWhereOrNull' in at('lib/data/repositories/habit_repository.dart', 34, 'ERR-001')[0]['note']"
assert "K1-E2 TP: network try returning null still ERR-007"              "$TMP/m.json" "at('lib/data/repositories/habit_repository.dart', 45, 'ERR-007')"
assert "K1-E3: bool capability probe is ERR-001 low"                     "$TMP/m.json" "at('lib/data/services/biometric_service.dart', 10, 'ERR-001')[0]['severity'] == 'low'"
assert "K1-E3 TP: non-probe default still ERR-001 high"                  "$TMP/m.json" "at('lib/data/services/biometric_service.dart', 20, 'ERR-001')[0]['severity'] == 'high'"
assert "K1 ERR-008: condition skipped, one finding per catch block"      "$TMP/m.json" "[f['line'] for f in d['findings'] if f['id'] == 'ERR-008'] == [20]"
assert "K1 FN: State class with setState loading + unguarded await"      "$TMP/m.json" "at('lib/ui/sync/widgets/sync_screen.dart', 18, 'ERR-010')[0]['note'].startswith('setState:') and len([f for f in d['findings'] if f['id'] == 'ERR-010' and 'sync_screen' in f['file']]) == 1"

X=lib/x/bloc
python3 -I "$CHECK" "$FIX/calib_bloc" --json > "$TMP/k2.json"
assert "K2-E1: emit.forEach(onError:) is handled"                        "$TMP/k2.json" "not at('$X/y_bloc.dart', 20, 'ERR-010')"
assert "K2-E1 TP: emit.forEach without onError still ERR-010"            "$TMP/k2.json" "at('$X/y_bloc.dart', 30, 'ERR-010')[0]['severity'] == 'high'"
assert "K2-E2: catchError that emits a failure is handled"               "$TMP/k2.json" "not at('$X/x_cubit.dart', 11, 'ERR-010') and not at('$X/x_cubit.dart', 12, 'ERR-010')"
assert "K2-E2: catchError that doesn't emit is ERR-010 medium"           "$TMP/k2.json" "at('$X/x_cubit.dart', 18, 'ERR-010')[0]['severity'] == 'medium'"
assert "K2-FN-3: catchError((e) => ...e.toString()) is ERR-008 (low)"    "$TMP/k2.json" "at('$X/x_cubit.dart', 12, 'ERR-008')[0]['severity'] == 'low'"
assert "K2-FN-4: copyWith(status: () => X.loading) is a loading state"   "$TMP/k2.json" "at('$X/x_cubit.dart', 26, 'ERR-010')[0]['severity'] == 'high'"
assert "K2: awaiting a repository that cannot fail is not ERR-010"       "$TMP/k2.json" "not [f for f in d['findings'] if 'new_car' in f['file']]"
assert "K2: _tryGetUser catch -> null is info"                           "$TMP/k2.json" "at('lib/authentication/bloc/authentication_bloc.dart', 21, 'ERR-001')[0]['severity'] == 'info'"
assert "K2 TP: plain method catch -> null still high"                    "$TMP/k2.json" "at('lib/authentication/bloc/authentication_bloc.dart', 32, 'ERR-001')[0]['severity'] == 'high'"
assert "K2: best-effort jumpTo catch is low"                             "$TMP/k2.json" "at('lib/chat/view/chat_page.dart', 16, 'ERR-001')[0]['severity'] == 'low'"
assert "K2 ERR-004: narrow typed catch evidence names what it catches"   "$TMP/k2.json" "'catch only ServerException' in at('lib/data/repositories/thing_repository_impl.dart', 16, 'ERR-004')[0]['evidence'] and 'does not cover' in at('lib/data/repositories/thing_repository_impl.dart', 16, 'ERR-004')[0]['note']"
assert "K2: no false highs besides the two TPs"                          "$TMP/k2.json" "sorted((f['file'].split('/')[-1], f['line']) for f in d['findings'] if f['severity'] == 'high') == [('authentication_bloc.dart', 32), ('x_cubit.dart', 26), ('y_bloc.dart', 30)]"

python3 -I "$CHECK" "$FIX/calib_riverpod" --json --profile riverpod > "$TMP/k3.json"
assert "K3-E1: xOrNull catch -> null is info"                            "$TMP/k3.json" "at('lib/src/utils/json.dart', 18, 'ERR-001')[0]['severity'] == 'info'"
assert "K3-E1 TP: same body without the OrNull contract still high"      "$TMP/k3.json" "at('lib/src/utils/json.dart', 27, 'ERR-001')[0]['severity'] == 'high'"
assert "K3-E2: bool probes (isX, or try ends in return true) are low"    "$TMP/k3.json" "[f['severity'] for f in d['findings'] if f['file'] == 'lib/src/network/connectivity.dart'] == ['low', 'low']"
assert "K3-E3: logging, comparisons and unrelated e are not ERR-008"     "$TMP/k3.json" "sorted(f['line'] for f in d['findings'] if f['id'] == 'ERR-008') == [17, 34]"
assert "K3-E4: graded by class: notifier low, widget medium"             "$TMP/k3.json" "at('lib/src/view/home_screen.dart', 17, 'ERR-008')[0]['severity'] == 'low' and at('lib/src/view/home_screen.dart', 34, 'ERR-008')[0]['severity'] == 'medium'"
assert "K3-E5: flag reset in finally is not ERR-010"                     "$TMP/k3.json" "'ERR-010' not in ids"
assert "K3-E6: repository behind a FutureProvider is ERR-004 low"        "$TMP/k3.json" "at('lib/src/model/pub_repository.dart', 11, 'ERR-004')[0]['severity'] == 'low' and 'ERR-008' in at('lib/src/model/pub_repository.dart', 11, 'ERR-004')[0]['note']"
python3 -I "$CHECK" "$FIX/calib_riverpod" --json --profile mvn > "$TMP/k3m.json"
assert "K3-E6: only under plain riverpod (mvn keeps medium)"             "$TMP/k3m.json" "at('lib/src/model/pub_repository.dart', 11, 'ERR-004')[0]['severity'] == 'medium'"

G=lib/app/modules/login/controllers/login_controller.dart
python3 -I "$CHECK" "$FIX/calib_getx" --json --profile getx > "$TMP/g.json"
assert "K3-E7: Get.snackbar / *Toast* in logic are UI severity"          "$TMP/g.json" "at('$G', 15, 'ERR-008')[0]['severity'] == 'medium' and at('$G', 23, 'ERR-008')[0]['severity'] == 'medium'"
assert "K3-E7: stored in an observable stays low"                        "$TMP/g.json" "at('$G', 32, 'ERR-008')[0]['severity'] == 'low'"

python3 -I "$CHECK" "$FIX/calib_setstate" --json > "$TMP/st.json"
assert "K3 FN: unguarded network await in a State callback is ERR-014"   "$TMP/st.json" "[(f['id'], f['line'], f['severity']) for f in d['findings']] == [('ERR-014', 22, 'medium')]"

# --- files[] roles from arch_check (repository, barrel, di, unknown) and files[] as scope, via a stub
mkdir -p "$TMP/stub/skills/flutter-error-handling/scripts" "$TMP/stub/skills/flutter-architecture/scripts"
cp "$CHECK" "$TMP/stub/skills/flutter-error-handling/scripts/check_errors.py"
cp "$HERE/stub_arch_check.py" "$TMP/stub/skills/flutter-architecture/scripts/arch_check.py"
python3 -I "$TMP/stub/skills/flutter-error-handling/scripts/check_errors.py" "$FIX/roles" --json > "$TMP/r.json"
assert "roles: stub arch_check is used"                                  "$TMP/r.json" "d['classification'] == 'arch_check files[]' and d['profile']['presentation'] == 'bloc'"
assert "roles: 'repository' gets ERR-004 and ERR-007 like an impl"       "$TMP/r.json" "at('lib/cart/cart_repository.dart', 8, 'ERR-004') and at('lib/cart/cart_repository.dart', 17, 'ERR-007')"
assert "roles: 'barrel' and 'di' files are skipped"                      "$TMP/r.json" "not [f for f in d['findings'] if f['file'] in ('lib/cart/bloc/bloc.dart', 'lib/di/providers.dart')] and d['stats']['skipped_roles'] == 2"
assert "roles: an unknown role is tolerated"                             "$TMP/r.json" "at('lib/misc/weird.dart', 3, 'ERR-005')"
assert "roles: files outside files[] are out of scope"                   "$TMP/r.json" "not [f for f in d['findings'] if f['file'] == 'lib/gen/out.dart'] and d['stats']['skipped_out_of_scope'] == 1"

# --- --profile override
python3 -I "$CHECK" "$FIX/bloc_violations" --json --profile mvvm > "$TMP/p.json"
assert "--profile overrides detection" "$TMP/p.json" "d['profile']['presentation'] == 'mvvm' and d['profile']['source'].startswith('declared')"

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

[ $fail = 0 ] && echo "ALL flutter-error-handling TESTS PASSED" || echo "flutter-error-handling: SOME TESTS FAILED"
exit $fail
