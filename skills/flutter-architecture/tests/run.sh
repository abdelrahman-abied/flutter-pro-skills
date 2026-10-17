#!/usr/bin/env bash
# Regression tests for scripts/arch_check.py.
# Needs bash 3.2+ and python3 >= 3.8 (stdlib only). No Flutter/Dart SDK, no pub get.
# Prints PASS/FAIL lines; exits 1 on any failure.
set -u

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CHECK="$HERE/../scripts/arch_check.py"
FIX="$HERE/fixtures"
TMP="$(mktemp -d "${TMPDIR:-/tmp}/arch-tests.XXXXXX")"
trap 'rm -rf "$TMP"' EXIT
PASS=0
FAIL=0

pass() { PASS=$((PASS + 1)); echo "PASS $1"; }
fail() { FAIL=$((FAIL + 1)); echo "FAIL $1"; if [ -n "${2:-}" ]; then echo "     $2"; fi; }
expect() { # label got want
  if [ "$2" == "$3" ]; then pass "$1"; else fail "$1" "want [$3] got [$2]"; fi
}

# run_json <name> <fixture-dir> [args...]  ->  $TMP/<name>.json
run_json() {
  local name="$1" dir="$2"
  shift 2
  python3 -I "$CHECK" "$dir" --json "$@" > "$TMP/$name.json" 2> "$TMP/$name.err"
  local rc=$?
  if [ $rc -ne 0 ]; then fail "$name: exit code" "exit $rc: $(head -c 300 "$TMP/$name.err")"; fi
}

# q <name> <query>   queries: profile | clean | layout | ids | count:ID | sev:ID | supp | supp_list
#                             | has:ID:FILE:LINE | files | evidence:ID | signal0 | keys
q() {
  python3 -I - "$TMP/$1.json" "$2" <<'PY'
import json, sys
r = json.load(open(sys.argv[1]))
qq = sys.argv[2]
v = r['violations']
if qq == 'profile':
    print(r['profile']['presentation'])
elif qq == 'clean':
    print(str(r['profile']['clean_architecture']).lower())
elif qq == 'layout':
    print(r['profile']['layout'])
elif qq == 'ids':
    print(','.join(sorted({x['id'] for x in v})))
elif qq.startswith('count:'):
    print(sum(1 for x in v if x['id'] == qq[6:]))
elif qq.startswith('sev:'):
    print(','.join(sorted({x['severity'] for x in v if x['id'] == qq[4:]})))
elif qq == 'supp':
    print(len(r['suppressed']))
elif qq == 'supp_list':
    print(' '.join('%s@%s:%d' % (s['id'], s['file'].rsplit('/', 1)[-1], s['line']) for s in r['suppressed']))
elif qq.startswith('has:'):
    _, rid, f, ln = qq.split(':')
    print('yes' if any(x['id'] == rid and x['file'].endswith(f) and x['line'] == int(ln) for x in v) else 'no')
elif qq == 'files':
    print(','.join(sorted({x['file'].rsplit('/', 1)[-1] for x in v})))
elif qq.startswith('fcount:'):
    _, rid, suf = qq.split(':', 2)
    print(sum(1 for x in v if x['id'] == rid and x['file'].endswith(suf)))
elif qq.startswith('fsev:'):
    _, rid, suf = qq.split(':', 2)
    print(','.join(sorted({x['severity'] for x in v if x['id'] == rid and x['file'].endswith(suf)})))
elif qq.startswith('fnote:'):
    _, rid, suf = qq.split(':', 2)
    print(' | '.join(x['note'] for x in v if x['id'] == rid and x['file'].endswith(suf)))
elif qq.startswith('role:'):
    print(','.join(x['role'] for x in r['files'] if x['file'].endswith(qq[5:])) or 'none')
elif qq.startswith('layer:'):
    print(','.join(x['layer'] for x in r['files'] if x['file'].endswith(qq[6:])) or 'none')
elif qq == 'conf':
    print(r['profile']['confidence'])
elif qq == 'pairs':
    keys = {}
    for x in v:
        keys.setdefault((x['file'], x['line']), set()).add(x['id'])
    print(sum(1 for ids in keys.values() if {'ARCH-005', 'ARCH-008'} <= ids or {'ARCH-007', 'ARCH-012'} <= ids))
elif qq.startswith('notes:'):
    print('\n'.join(x['note'] for x in v if x['id'] == qq[6:]))
elif qq.startswith('evidence:'):
    print(' | '.join(x['evidence'] for x in v if x['id'] == qq[9:]))
elif qq == 'signals':
    print('; '.join(r['profile']['signals']))
elif qq == 'signal0':
    print(r['profile']['signals'][0] if r['profile']['signals'] else '')
elif qq == 'keys':
    ok = []
    ok.append(set(r) == {'schema', 'root', 'package', 'profile', 'stats', 'files', 'violations', 'suppressed'})
    ok.append(r['schema'] == 'flutter-pro-skills/arch-profile@1')
    ok.append(set(r['profile']) == {'presentation', 'clean_architecture', 'repository_pattern', 'use_cases',
                                     'layout', 'state_management', 'di', 'confidence', 'signals'})
    ok.append(r['profile']['confidence'] in ('high', 'medium', 'low'))
    ok.append(r['profile']['layout'] in ('feature-first', 'layer-first', 'hybrid'))
    ok.append(isinstance(r['profile']['state_management'], list) and isinstance(r['profile']['di'], list))
    ok.append(set(r['stats']) == {'files', 'by_layer', 'features'} and isinstance(r['stats']['files'], int))
    ok.append(all(set(x) == {'id', 'name', 'severity', 'file', 'line', 'evidence', 'message', 'note'}
                  and isinstance(x['line'], int) and x['severity'] in ('high', 'medium', 'low') for x in v))
    ok.append(all(set(s) == {'id', 'file', 'line', 'reason'} for s in r['suppressed']))
    ok.append(bool(v) and bool(r['suppressed']))
    ok.append(isinstance(r['files'], list) and len(r['files']) == r['stats']['files'] and all(
        set(x) == {'file', 'layer', 'role', 'feature', 'classes'} and x['file'].startswith('lib/')
        and isinstance(x['classes'], list) and (x['feature'] is None or isinstance(x['feature'], str))
        for x in r['files']))
    ok.append([x['file'] for x in r['files']] == sorted(x['file'] for x in r['files']))
    print('ok' if all(ok) else 'bad:' + ''.join('1' if o else '0' for o in ok))
elif qq.startswith('file:'):
    # file:<suffix>  ->  layer|role|feature|Class1,Class2
    hits = [x for x in r['files'] if x['file'].endswith(qq[5:])]
    print(' ; '.join('%s|%s|%s|%s' % (x['layer'], x['role'], x['feature'] or '-', ','.join(x['classes']))
                     for x in hits) or 'none')
elif qq == 'nfiles':
    print(len(r['files']))
elif qq == 'baseline':
    b = r.get('baseline') or {}
    print('%s/%s/%s' % (b.get('new'), b.get('baselined'), b.get('fixed')))
elif qq == 'ci':
    c = r.get('ci') or {}
    print('%s:%s:%s' % (c.get('fail_on'), c.get('at_or_above'), c.get('failed')))
PY
}

check_fixture() { # name presentation expected-ids [clean] [layout]
  local name="$1"
  run_json "$name" "$FIX/$name"
  expect "$name: profile" "$(q "$name" profile)" "$2"
  expect "$name: violation ids" "$(q "$name" ids)" "$3"
  if [ -n "${4:-}" ]; then expect "$name: clean_architecture" "$(q "$name" clean)" "$4"; fi
  if [ -n "${5:-}" ]; then expect "$name: layout" "$(q "$name" layout)" "$5"; fi
}

SNAP_BEFORE="$(cd "$FIX" && find . -type f | sort | xargs cksum)"

# ---------------------------------------------------------------- clean fixtures
check_fixture mvn_clean mvn "" true feature-first
expect "mvn_clean: DI seams suppressed" "$(q mvn_clean supp_list)" \
  "ARCH-001@movie_usecase.dart:7 ARCH-001@settings_usecase.dart:5"
check_fixture mvvm_clean mvvm "" false layer-first
# Benchmark regression: canonical bloclibrary flutter_weather shape (pages navigate to other features' pages,
# settings reads the weather bloc, ThemeCubit imports material for Color). Only the 2 planted real violations.
check_fixture calib_bloc_weather bloc "ARCH-005,ARCH-010" false hybrid
expect "mvvm_clean: nothing suppressed" "$(q mvvm_clean supp)" "0"
check_fixture bloc_clean bloc "" false feature-first
expect "bloc_clean: nothing suppressed" "$(q bloc_clean supp)" "0"

# ---------------------------------------------------------------- violation fixtures
check_fixture mvn_violations mvn \
  "ARCH-001,ARCH-002,ARCH-003,ARCH-004,ARCH-005,ARCH-006,ARCH-008,ARCH-009,ARCH-012,ARCH-102,ARCH-105,ARCH-106,ARCH-107,ARCH-108,ARCH-109,ARCH-110,ARCH-111,ARCH-112" \
  true feature-first
# one report per import (CONTRACTS 18): the notifier's dio import was ARCH-007 + ARCH-012; ARCH-012 is kept
expect "mvn_violations: ARCH-007 folded into ARCH-012 on the same import" \
  "$(q mvn_violations notes:ARCH-012 | grep -c 'also ARCH-007')" 1
expect "mvn_violations: ARCH-001 entity imports DTO" "$(q mvn_violations has:ARCH-001:domain/entities/movie_entity.dart:4)" yes
expect "mvn_violations: ARCH-003 severities (material medium, foundation low)" "$(q mvn_violations sev:ARCH-003)" "low,medium"
expect "mvn_violations: ARCH-003 foundation is low" "$(q mvn_violations has:ARCH-003:movie_entity.dart:1)" yes
expect "mvn_violations: ARCH-003 dio in use case" "$(q mvn_violations has:ARCH-003:movie_usecase.dart:1)" yes
expect "mvn_violations: ARCH-005 count (dio + source; http suppressed)" "$(q mvn_violations count:ARCH-005)" 2
expect "mvn_violations: ARCH-012 count" "$(q mvn_violations count:ARCH-012)" 2
expect "mvn_violations: ARCH-102 count" "$(q mvn_violations count:ARCH-102)" 2
expect "mvn_violations: ARCH-105 top-level + static" "$(q mvn_violations count:ARCH-105)" 2
expect "mvn_violations: ARCH-106 count" "$(q mvn_violations count:ARCH-106)" 2
expect "mvn_violations: ARCH-111 at showErrorDialog" "$(q mvn_violations has:ARCH-111:movie_state.dart:5)" yes
expect "mvn_violations: ARCH-112 folder + 2 classes (AnimationController subclass exempt)" "$(q mvn_violations count:ARCH-112)" 3
expect "mvn_violations: suppressions (seam, line, file)" "$(q mvn_violations supp_list)" \
  "ARCH-001@movie_usecase.dart:6 ARCH-005@movie_view.dart:5 ARCH-008@movie_tile.dart:4"

check_fixture mvvm_violations mvvm \
  "ARCH-005,ARCH-006,ARCH-007,ARCH-008,ARCH-010,ARCH-011,ARCH-104,ARCH-107" false layer-first
expect "mvvm_violations: ARCH-010 is low under mvvm" "$(q mvvm_violations sev:ARCH-010)" low
expect "mvvm_violations: ARCH-011 impl->other repo, own contract exempt" "$(q mvvm_violations evidence:ARCH-011)" \
  "import '../cart/cart_repository.dart';"

check_fixture bloc_violations bloc "ARCH-008,ARCH-009,ARCH-010,ARCH-102,ARCH-106,ARCH-111" false layer-first
expect "bloc_violations: ARCH-010 is medium under bloc" "$(q bloc_violations sev:ARCH-010)" medium

# material imported only for Colors is idiomatic in a GetX controller (K3 A11): no ARCH-009 here any more;
# calib_getx_ui asserts that real UI use is still reported (low)
check_fixture getx_or_mvc_violations getx "ARCH-010,ARCH-014,ARCH-113" false feature-first
expect "getx: ARCH-113 put + find in build" "$(q getx_or_mvc_violations count:ARCH-113)" 2

check_fixture setstate_violations setstate "ARCH-005,ARCH-101,ARCH-103,ARCH-105" false layer-first
expect "setstate: ARCH-101 ignores comments and strings" "$(q setstate_violations count:ARCH-101)" 3
expect "setstate: ARCH-105 (4 top-level + 1 static; State static exempt)" "$(q setstate_violations count:ARCH-105)" 5
expect "setstate: ARCH-103 god view" "$(q setstate_violations evidence:ARCH-103)" "531 lines (limit 500 for view)"

check_fixture feature_first_violations riverpod "ARCH-013,ARCH-014,ARCH-015" false feature-first
expect "feature_first: cycle path" "$(q feature_first_violations evidence:ARCH-015)" "auth → profile → auth"

check_fixture parsing_edge_cases unknown "ARCH-005" false layer-first
expect "parsing: conditional + deferred imports resolved, commented/string imports ignored" \
  "$(q parsing_edge_cases has:ARCH-005:home_view.dart:1)$(q parsing_edge_cases has:ARCH-005:home_view.dart:4)$(q parsing_edge_cases count:ARCH-005)" \
  "yesyes2"

# ---------------------------------------------------------------- regressions reported by other agents
# get_cli layout: lib/app/modules/<m>/controllers|views|bindings are not the composition root
check_fixture getx_cli_violations getx "ARCH-007,ARCH-009,ARCH-102" false feature-first
expect "getx_cli: controller importing dio is reported" "$(q getx_cli_violations has:ARCH-007:modules/home/controllers/home_controller.dart:1)" yes
expect "getx_cli: BuildContext + ScaffoldMessenger in controller" "$(q getx_cli_violations count:ARCH-102)" 2
# one lib/features/<f> folder is feature-first, and no contradicting "flat lib/" signal
check_fixture single_feature setstate "" false feature-first
case "$(q single_feature signals)" in
  *flat*) fail "single_feature: signals agree with layout" "$(q single_feature signals)" ;;
  *) pass "single_feature: signals agree with layout" ;;
esac
# ARCH-111 only flags one-time-event names; showPassword/showArchived/showDetails/isExpanded/openNow are toggles
expect "mvn_violations: ARCH-111 ignores persistent UI toggles" "$(q mvn_violations count:ARCH-111)" 1
expect "bloc_violations: ARCH-111 still flags shouldNavigate*" "$(q bloc_violations count:ARCH-111)" 1

# ---------------------------------------------------------------- calibration regressions (CONTRACTS section 18)
# K1: Flutter MVVM (compass shapes)
F=calib_mvvm_compass
run_json $F "$FIX/$F"
expect "$F: mvvm" "$(q $F profile)" mvvm
expect "$F: A1 use case -> data/repositories contract is not ARCH-001" "$(q $F count:ARCH-001)" 0
expect "$F: A2 view model built from context.read is not ARCH-008" "$(q $F fcount:ARCH-008:home_screen_container.dart)" 0
expect "$F: TP kept, widget calling the repository is ARCH-008" "$(q $F fcount:ARCH-008:booking_list.dart)" 1
expect "$F: A6 material for value types only is not reported (benchmark: agents repeated the low hit)" "$(q $F fsev:ARCH-009:home_viewmodel.dart)" ""
expect "$F: TP kept, a view model building widgets is ARCH-009 medium" "$(q $F fsev:ARCH-009:dialog_viewmodel.dart)" medium
expect "$F: A5 never-reassigned statics low, reassigned medium" "$(q $F fsev:ARCH-105:theme.dart)" "low,medium"
expect "$F: lib/config/ is the composition root" "$(q $F layer:config/dependencies.dart)" app
expect "$F: ARCH-002 medium when the ui/ target declares no widget" "$(q $F sev:ARCH-002)" medium
expect "$F: ARCH-003 low for value types under mvvm" "$(q $F sev:ARCH-003)" low

# K1: Provider app (Habo shapes) + FX-T router glue
F=calib_provider_habo
run_json $F "$FIX/$F"
expect "$F: FN1 ChangeNotifier manager is logic" "$(q $F role:habits/habits_manager.dart)" logic
expect "$F: FN1 TPs now reported (ARCH-102, ARCH-009)" "$(q $F fcount:ARCH-102:habits_manager.dart):$(q $F fsev:ARCH-009:habits_manager.dart)" "3:medium"
expect "$F: A3 no ARCH-011 for a barrel or a factory" "$(q $F count:ARCH-011)" 0
expect "$F: roles barrel / di / impl / di locator" \
  "$(q $F role:repositories/repositories.dart)/$(q $F role:repository_factory.dart)/$(q $F role:sqlite_habit_repository.dart)/$(q $F role:service_locator.dart)" \
  "barrel/di/repository-impl/di"
expect "$F: A4 bootstrap I/O in main() is not ARCH-101" "$(q $F fcount:ARCH-101:lib/main.dart)" 0
expect "$F: FN2 hand-rolled locator in UI is ARCH-104" "$(q $F has:ARCH-104:sync_screen.dart:15)" yes
expect "$F: FN3 Supabase.instance in a widget is ARCH-101" "$(q $F has:ARCH-101:profile_screen.dart:9)" yes
expect "$F: RouterDelegate with ChangeNotifier is composition root, not logic" "$(q $F file:navigation/app_router.dart)" "app|other|-|AppRouter"

# K2: Bloc majority, DI sites, accessor idiom, feature folders
F=calib_bloc_mixed
run_json $F "$FIX/$F"
expect "$F: P1 bloc majority beats one GetxController, never high" "$(q $F profile):$(q $F conf)" "bloc:medium"
case "$(q $F signals)" in *"AP-mixed-architecture"*"path packages: todos_repository (not scanned)"*) pass "$F: P1/P4 signals" ;;
  *) fail "$F: P1/P4 signals" "$(q $F signals)" ;; esac
expect "$F: C1 concrete repository has role repository" "$(q $F role:lib/shopping_repository.dart)" repository
expect "$F: C1 cubit -> concrete repository is not ARCH-007" "$(q $F fcount:ARCH-007:cart_cubit.dart)" 0
expect "$F: C1/C5 BlocProvider(create:) DI site: no ARCH-005/008/104 in cart_page" \
  "$(q $F fcount:ARCH-005:cart_page.dart)$(q $F fcount:ARCH-008:cart_page.dart)$(q $F fcount:ARCH-104:cart_page.dart)" "000"
expect "$F: C1 concrete repository used in a view is ARCH-008 (not ARCH-005)" \
  "$(q $F fcount:ARCH-008:cart_badge.dart):$(q $F fcount:ARCH-005:cart_badge.dart)" "1:0"
expect "$F: FN-2 get_it alias in UI is ARCH-104" "$(q $F has:ARCH-104:cart_badge.dart:10)" yes
expect "$F: C2 transport built for injection is ARCH-005 low" "$(q $F fsev:ARCH-005:posts_page.dart)" low
expect "$F: TP kept, bloc doing HTTP is ARCH-007" "$(q $F fsev:ARCH-007:post_bloc.dart)" medium
expect "$F: C6 accessor idiom is one low ARCH-102 and no ARCH-009" \
  "$(q $F fcount:ARCH-102:cart_cubit.dart):$(q $F fsev:ARCH-102:cart_cubit.dart):$(q $F fcount:ARCH-009:cart_cubit.dart)" "1:low:0"
expect "$F: C7 ChangeNotifier in *_state.dart is logic, no ARCH-106" "$(q $F role:theme_state.dart):$(q $F count:ARCH-106)" "logic:0"
expect "$F: P2 bloclibrary feature folders" "$(q $F layout):$(python3 -I -c 'import json,sys; print(",".join(json.load(open(sys.argv[1]))["stats"]["features"]))' "$TMP/$F.json")" "feature-first:cart,home,posts"
expect "$F: P3 feature models are presentation/other" "$(q $F file:cart/models/item.dart)" "presentation|other|cart|Item"
expect "$F: P5 lib/app.dart is the composition root" "$(q $F layer:lib/app.dart):$(q $F fcount:ARCH-005:lib/app.dart)" "app:0"

F=calib_bloc_barrels
run_json $F "$FIX/$F"
expect "$F: C3 barrel role, own barrel is not ARCH-010" "$(q $F role:x/bloc/bloc.dart):$(q $F fcount:ARCH-010:x_bloc.dart)" "barrel:0"
expect "$F: FN-5 bloc -> other bloc through a barrel is ARCH-010" "$(q $F fcount:ARCH-010:y_bloc.dart)" 1
expect "$F: C4 package barrel exporting its repository is not ARCH-011" "$(q $F count:ARCH-011):$(q $F role:lib/todos_repository.dart)" "0:barrel"
expect "$F: FN-1 repositories_impl/*_repo_impl.dart is an impl" "$(q $F role:post_repo_impl.dart)" repository-impl
expect "$F: lib/src/ is stripped (src/models -> data)" "$(q $F layer:src/models/todo.dart)" data

# K3: plain Riverpod
F=calib_riverpod
run_json $F "$FIX/$F"
expect "$F: A2/A3/A15 neutral provider, static namespace, Function field: no ARCH-005" "$(q $F fcount:ARCH-005:users_screen.dart)" 0
expect "$F: TP kept, constructing the service in a widget is ARCH-005 high" "$(q $F fsev:ARCH-005:direct_screen.dart)" high
expect "$F: A5 co-located provider I/O: only a low exception-type ARCH-005, no ARCH-101" \
  "$(q $F fsev:ARCH-005:characters_screen.dart):$(q $F fcount:ARCH-101:characters_screen.dart)" "low:0"
expect "$F: A9 jsonDecode only on a response body" "$(q $F fcount:ARCH-101:json_screen.dart):$(q $F has:ARCH-101:json_screen.dart:12)" "1:yes"
expect "$F: FN call shapes widget.httpClient!.post( and Socket.connect(" "$(q $F fcount:ARCH-101:http_widget.dart)" 2
expect "$F: A10 *_controller.dart with only widgets is a widget" "$(q $F role:animation_controller.dart)" widget
expect "$F: A4 CancelToken / provider-injected service: no ARCH-007" "$(q $F fcount:ARCH-007:home_notifier.dart)" 0
expect "$F: TP kept, notifier constructing a service is ARCH-007" "$(q $F fcount:ARCH-007:direct_notifier.dart)" 1
expect "$F: A17 extension on BuildContext is not ARCH-102" "$(q $F count:ARCH-102)" 0
expect "$F: A12 ref.read in a registered listener is fine, a direct call is ARCH-110" \
  "$(q $F count:ARCH-110):$(q $F has:ARCH-110:home_page.dart:27)" "1:yes"
expect "$F: A6 provider-only file is di" "$(q $F role:user_repository_providers.dart)" di
expect "$F: A7 base class / static helper are not ARCH-011" "$(q $F count:ARCH-011)" 0
expect "$F: FN-7 SDK type returned by a repository is ARCH-107" "$(q $F has:ARCH-107:user_repository.dart:6)" yes
expect "$F: dotted name jobs.repository.dart" "$(q $F role:jobs.repository.dart)" repository
expect "$F: A15 analytics service is core" "$(q $F file:analytics_service.dart)" "core|other|-|AnalyticsService"
expect "$F: A14 *_event.dart away from bloc/ is not an event" "$(q $F role:socket_event.dart)" other

F=calib_riverpod_features
run_json $F "$FIX/$F"
expect "$F: K3 MVN rule, codegen *Notifier without use cases is riverpod" "$(q $F profile)" riverpod
case "$(q $F signals)" in *"plain Riverpod naming, not MVN"*"use cases: 0 files"*) pass "$F: MVN naming signals" ;;
  *) fail "$F: MVN naming signals" "$(q $F signals)" ;; esac
expect "$F: A8 l10n arb-dir output, *.gen.dart and 'Generated by' headers skipped" "$(q $F nfiles)" 8
expect "$F: ARCH-015 once per strongly connected component" "$(q $F count:ARCH-015)" 1
case "$(q $F fnote:ARCH-015:a_page.dart)" in *"3 mutually dependent features"*) pass "$F: ARCH-015 note names the SCC" ;;
  *) fail "$F: ARCH-015 note names the SCC" "$(q $F fnote:ARCH-015:a_page.dart)" ;; esac
expect "$F: A13 provider-only cross-feature import is not ARCH-014; a page import is" \
  "$(q $F fcount:ARCH-014:a_page.dart):$(q $F fcount:ARCH-014:c_controller.dart)" "0:1"
expect "$F: A16 application/ service is a use case" "$(q $F role:application/c_service.dart)" usecase
expect "$F: lib/src/features/<f> is a feature" "$(q $F file:a/presentation/a_page.dart)" "presentation|view|a|APage"

F=calib_mvn_dedupe
run_json $F "$FIX/$F"
expect "$F: K3 MVN rule, notifier/ + use cases is mvn/high" "$(q $F profile):$(q $F conf)" "mvn:high"
expect "$F: one report per import (005/008, 012/007)" "$(q $F pairs):$(q $F ids)" "0:ARCH-005,ARCH-012"
expect "$F: the folded rule is named in the note" "$(q $F fnote:ARCH-005:movie_view.dart)|$(q $F fnote:ARCH-012:movie_notifier.dart)" \
  "also ARCH-008|also ARCH-007"
expect "mvn_clean: MVN high with use cases" "$(q mvn_clean conf)" high

F=calib_getx_ui
run_json $F "$FIX/$F"
expect "$F: A11 Colors/TextEditingController in a GetX controller is not ARCH-009" "$(q $F fcount:ARCH-009:home_controller.dart)" 0
expect "$F: real UI in a GetX controller is ARCH-009 low" "$(q $F fsev:ARCH-009:dialog_controller.dart)" low
expect "$F: GetX bindings/ are the composition root" "$(q $F layer:bindings/home_binding.dart)" app

# ---------------------------------------------------------------- every rule is covered
ALL_IDS="ARCH-001 ARCH-002 ARCH-003 ARCH-004 ARCH-005 ARCH-006 ARCH-007 ARCH-008 ARCH-009 ARCH-010 ARCH-011 ARCH-012 ARCH-013 ARCH-014 ARCH-015 ARCH-101 ARCH-102 ARCH-103 ARCH-104 ARCH-105 ARCH-106 ARCH-107 ARCH-108 ARCH-109 ARCH-110 ARCH-111 ARCH-112 ARCH-113"
SEEN=""
for n in mvn_violations mvvm_violations bloc_violations getx_or_mvc_violations setstate_violations feature_first_violations; do
  SEEN="$SEEN,$(q "$n" ids)"
done
MISSING=""
for id in $ALL_IDS; do
  case ",$SEEN," in *",$id,"*) ;; *) MISSING="$MISSING $id" ;; esac
done
expect "coverage: every rule ID triggered by a violations fixture" "${MISSING# }" ""

# ---------------------------------------------------------------- CLI options
printf 'lib/features/movie/presentation/view/movie_view.dart\n\n' > "$TMP/scope.txt"
run_json files_scope "$FIX/mvn_violations" --files "$TMP/scope.txt"
expect "--files: only the listed file is reported" "$(q files_scope files)" "movie_view.dart"
expect "--files: its rules" "$(q files_scope ids)" "ARCH-005,ARCH-006,ARCH-008,ARCH-110"
expect "--files: suppressed limited too" "$(q files_scope supp_list)" "ARCH-005@movie_view.dart:5"

run_json override "$FIX/mvn_violations" --profile bloc
expect "--profile: overrides presentation" "$(q override profile)" bloc
expect "--profile: signal records the declaration" "$(q override signal0)" "declared via --profile bloc (detected: mvn)"
expect "--profile bloc: mvn-only rules gone" "$(q override count:ARCH-012)$(q override count:ARCH-112)" "00"
run_json override2 "$FIX/mvn_clean" --profile mvvm
# riverpod_annotation in domain/usecases/ is allowed only under mvn (CONTRACTS ARCH-003)
expect "--profile mvvm on mvn_clean: mvn allowances no longer apply" "$(q override2 profile):$(q override2 ids)" "mvvm:ARCH-003"

run_json schema "$FIX/mvn_violations"
expect "--json: schema keys and types" "$(q schema keys)" ok

python3 -I "$CHECK" "$FIX/mvn_violations" --max 1 > "$TMP/text.txt" 2>&1
TXT_OK=1
grep -q '^== ARCHITECTURE PROFILE$' "$TMP/text.txt" || TXT_OK=0
grep -q '^== ARCHITECTURE VIOLATIONS$' "$TMP/text.txt" || TXT_OK=0
grep -q '^  presentation: mvn$' "$TMP/text.txt" || TXT_OK=0
grep -Eq '^  \[ARCH-[0-9]{3}\] [a-z-]+ \((high|medium|low)\) x[0-9]+ — .+' "$TMP/text.txt" || TXT_OK=0
grep -Eq '^      lib/[^ ]+:[0-9]+  .+' "$TMP/text.txt" || TXT_OK=0
grep -q '^  \[ARCH-112\] mvn-forbidden-naming (low) x3 — ' "$TMP/text.txt" || TXT_OK=0
grep -q '^      \.\.\. 2 more$' "$TMP/text.txt" || TXT_OK=0
[ "$(tail -n 1 "$TMP/text.txt")" == "  suppressed: 3 (see --json)" ] || TXT_OK=0
expect "text: section headers, group lines, --max, suppressed footer" "$TXT_OK" 1
python3 -I "$CHECK" "$FIX/mvn_clean" > "$TMP/clean.txt" 2>&1
expect "text: clean project prints none" "$(grep -c '^  none$' "$TMP/clean.txt")" 1

# ---------------------------------------------------------------- files array (CONTRACTS section 10)
expect "files: notifier classified" "$(q schema file:presentation/notifier/movie_notifier.dart)" "presentation|logic|movie|MovieNotifier"
expect "files: view lists widget + State classes" "$(q schema file:presentation/view/movie_view.dart)" "presentation|view|movie|MovieView,_MovieViewState"
expect "files: repository impl" "$(q schema file:data/repositories/movie_repository_impl.dart)" "data|repository-impl|movie|MovieRepositoryImpl"
expect "files: contract in domain" "$(q schema file:domain/repositories/movie_repository.dart)" "domain|repository-contract|movie|MovieRepository"
expect "files: composition root, no feature" "$(q schema file:lib/main.dart)" "app|other|-|"
CLS="$TMP/classes"
mkdir -p "$CLS/lib/features/cart/presentation/notifier" "$CLS/lib/generated"
printf 'name: classes\n' > "$CLS/pubspec.yaml"
cat > "$CLS/lib/features/cart/presentation/notifier/cart_notifier.dart" <<'DART'
/// class InDoc {}
@riverpod
class CartNotifier extends _$CartNotifier {
  int build() => 0;
}
mixin Loggable on Object {}
enum CartStatus { idle, busy }
abstract interface class Thing {}
mixin class Both {}
extension CartX on int {}
sealed class Ev {}
typedef Cb = void Function();
final s = 'class InString {}';
DART
echo 'class Gen {}' > "$CLS/lib/generated/x.dart"
echo 'class G {}' > "$CLS/lib/a.g.dart"
echo 'class F {}' > "$CLS/lib/a.freezed.dart"
run_json classes "$CLS"
expect "files: classes, mixins, enums only (no extension/typedef/comment/string)" \
  "$(q classes file:cart_notifier.dart)" "presentation|logic|cart|CartNotifier,Loggable,CartStatus,Thing,Both,Ev"
expect "files: generated files skipped" "$(q classes nfiles)" 1

# ---------------------------------------------------------------- CI mode: baseline, --ci, --fail-on
CI="$TMP/ci"
cp -R "$FIX/mvn_violations" "$CI"
BL="$TMP/baseline.json"
python3 -I "$CHECK" "$CI" --write-baseline "$BL" > "$TMP/wb.txt" 2>&1
expect "baseline: --write-baseline exits 0" "$?" 0
python3 -I - "$BL" "$TMP/schema.json" > "$TMP/bl_ok.txt" <<'PY'
import json, sys
b = json.load(open(sys.argv[1]))
r = json.load(open(sys.argv[2]))
ok = [set(b) == {'schema', 'entries'}, b['schema'] == 'flutter-pro-skills/arch-baseline@1',
      all(set(e) == {'id', 'file', 'key'} and all(isinstance(e[k], str) for k in e) for e in b['entries']),
      len(b['entries']) == len(r['violations']),
      not any(':%d' % v['line'] in e['key'] and False for e in b['entries'] for v in r['violations'])]
print('ok' if all(ok) else 'bad:' + ''.join('1' if o else '0' for o in ok))
PY
expect "baseline: schema, one entry per violation" "$(cat "$TMP/bl_ok.txt")" ok
grep -q 'wrote baseline' "$TMP/wb.txt"
expect "baseline: confirmation printed" "$?" 0

run_json bl_same "$CI" --baseline "$BL"
NV="$(python3 -I -c 'import json,sys; print(len(json.load(open(sys.argv[1]))["violations"]))' "$TMP/schema.json")"
expect "baseline: unchanged project has 0 new" "$(q bl_same count:ARCH-005):$(q bl_same baseline)" "0:0/$NV/0"
expect "baseline: nothing reported" "$(q bl_same ids)" ""

# move lines: prepend blank lines + a comment to every lib file -> still 0 new
find "$CI/lib" -name '*.dart' | while read -r f; do
  { printf '// moved\n\n\n'; cat "$f"; } > "$f.tmp" && mv "$f.tmp" "$f"
done
run_json bl_moved "$CI" --baseline "$BL"
expect "baseline: moved lines give no new violations" "$(q bl_moved baseline)" "0/$NV/0"

# add one new violation (a second dio import in a view) -> exactly 1 new
V="$CI/lib/features/movie/presentation/view/movie_view.dart"
{ printf "import 'package:shared_preferences/shared_preferences.dart';\n"; cat "$V"; } > "$V.tmp" && mv "$V.tmp" "$V"
run_json bl_new "$CI" --baseline "$BL"
expect "baseline: only the new violation is reported" "$(q bl_new ids):$(q bl_new baseline)" "ARCH-005:1/$NV/0"
expect "baseline: the new one is the added import" "$(q bl_new evidence:ARCH-005)" "import 'package:shared_preferences/shared_preferences.dart';"

# duplicates: 3 identical hits in a file, baseline has 2 -> exactly 1 new
DUP="$TMP/dup"
mkdir -p "$DUP/lib/features/x/presentation/notifier"
printf 'name: dup\ndependencies:\n  flutter_riverpod: any\n' > "$DUP/pubspec.yaml"
NF="$DUP/lib/features/x/presentation/notifier/x_notifier.dart"
M1='  void a() {\n    Navigator.of(c).pop();\n  }\n'
M2='  void b() {\n    Navigator.of(c).pop();\n  }\n'
M3='  void d() {\n    Navigator.of(c).pop();\n  }\n'
printf "class XNotifier {\n  XNotifier(this.c);\n  final BuildContext c;\n$M1$M2}\n" > "$NF"
python3 -I "$CHECK" "$DUP" --write-baseline "$TMP/dup.json" > /dev/null 2>&1
expect "baseline: duplicates stored once per occurrence" \
  "$(python3 -I -c 'import json,sys; e=json.load(open(sys.argv[1]))["entries"]; print(len(e), len({(x["id"],x["file"],x["key"]) for x in e}))' "$TMP/dup.json")" "3 2"
printf "class XNotifier {\n  XNotifier(this.c);\n  final BuildContext c;\n$M1$M2$M3}\n" > "$NF"
run_json dup_new "$DUP" --baseline "$TMP/dup.json"
expect "baseline: 3 identical hits vs 2 baselined = 1 new" "$(q dup_new count:ARCH-102):$(q dup_new baseline)" "1:1/3/0"
printf "class XNotifier {\n  XNotifier(this.c);\n  final BuildContext c;\n$M1}\n" > "$NF"
run_json dup_fixed "$DUP" --baseline "$TMP/dup.json"
expect "baseline: a fixed occurrence is counted, not reported" "$(q dup_fixed baseline)" "0/2/1"

# god-file key ignores the line count
GOD="$TMP/god"
cp -R "$FIX/setstate_violations" "$GOD"
python3 -I "$CHECK" "$GOD" --write-baseline "$TMP/god_bl.json" > /dev/null 2>&1
GV="$GOD/$(python3 -I -c 'import json,sys; print([e["file"] for e in json.load(open(sys.argv[1]))["entries"] if e["id"] == "ARCH-103"][0])' "$TMP/god_bl.json")"
printf '\n// grow\n' >> "$GV"
NG="$(python3 -I -c 'import json,sys; print(len(json.load(open(sys.argv[1]))["entries"]))' "$TMP/god_bl.json")"
run_json god "$GOD" --baseline "$TMP/god_bl.json"
expect "baseline: ARCH-103 survives a changed line count" "$(q god count:ARCH-103):$(q god baseline)" "0:0/$NG/0"

# --ci exit codes against mvn_violations (high + medium + low present)
python3 -I "$CHECK" "$FIX/mvn_violations" --ci > "$TMP/ci_text.txt" 2>&1
expect "--ci: default fail-on high exits 1" "$?" 1
python3 -I "$CHECK" "$FIX/mvn_violations" --ci --fail-on medium > /dev/null 2>&1
expect "--ci --fail-on medium exits 1" "$?" 1
python3 -I "$CHECK" "$FIX/mvn_violations" --ci --fail-on low > /dev/null 2>&1
expect "--ci --fail-on low exits 1" "$?" 1
python3 -I "$CHECK" "$FIX/mvn_clean" --ci --fail-on low > /dev/null 2>&1
expect "--ci on a clean project exits 0" "$?" 0
python3 -I "$CHECK" "$FIX/mvn_violations" > /dev/null 2>&1
expect "no --ci: findings still exit 0" "$?" 0
# only low findings left: high/medium pass, low fails
python3 -I "$CHECK" "$FIX/getx_or_mvc_violations" --ci --fail-on medium > /dev/null 2>&1
CI_RC=$?
python3 -I "$CHECK" "$FIX/getx_or_mvc_violations" --ci --fail-on low > /dev/null 2>&1
expect "--fail-on thresholds (getx fixture is low-only: medium passes, low fails)" "$CI_RC:$?" "0:1"
python3 -I "$CHECK" "$FIX/mvvm_violations" --files "$TMP/none.txt" --ci > /dev/null 2>&1
expect "--ci with an unreadable --files is a usage error" "$?" 2
printf 'lib/features/movie/presentation/controllers/movie_controller.dart\n' > "$TMP/low_only.txt"
python3 -I "$CHECK" "$FIX/mvn_violations" --files "$TMP/low_only.txt" --json --ci > "$TMP/low_only.json" 2>/dev/null
LOW_HIGH=$?
python3 -I "$CHECK" "$FIX/mvn_violations" --files "$TMP/low_only.txt" --ci --fail-on low > /dev/null 2>&1
LOW_LOW=$?
expect "--fail-on: a low-only scope passes high, fails low" "$(python3 -I -c 'import json,sys; print(sorted({v["severity"] for v in json.load(open(sys.argv[1]))["violations"]}))' "$TMP/low_only.json"):$LOW_HIGH:$LOW_LOW" "['low']:0:1"
python3 -I "$CHECK" "$CI" --baseline "$BL" --ci > /dev/null 2>&1
expect "--ci + baseline: the 1 new high violation fails" "$?" 1
python3 -I "$CHECK" "$FIX/mvn_violations" --baseline "$TMP/schema.json.missing" > /dev/null 2>&1
expect "exit 2: unreadable --baseline" "$?" 2
python3 -I "$CHECK" "$FIX/mvn_violations" --baseline "$TMP/schema.json" > /dev/null 2>&1
expect "exit 2: --baseline with the wrong schema" "$?" 2
python3 -I "$CHECK" "$FIX/mvn_violations" --ci --fail-on info > /dev/null 2>&1
expect "exit 2: bad --fail-on" "$?" 2
python3 -I "$CHECK" "$FIX/mvn_violations" --json --ci --fail-on medium > "$TMP/ci_json.json" 2>/dev/null
expect "--ci --json: exits 1" "$?" 1
expect "--ci --json: ci summary counts high+medium" "$(q ci_json ci)" "medium:$(python3 -I -c 'import json,sys; v=json.load(open(sys.argv[1]))["violations"]; print(sum(1 for x in v if x["severity"] in ("high","medium")))' "$TMP/schema.json"):True"
python3 -I "$CHECK" "$CI" --baseline "$BL" --ci > "$TMP/ci_bl.txt" 2>&1
expect "text: summary line 'N new, M baselined'" "$(grep -c "^  summary: 1 new, $NV baselined\$" "$TMP/ci_bl.txt")" 1
expect "text: ci verdict line" "$(grep -c '^  ci: fail (1 at or above high)$' "$TMP/ci_bl.txt")" 1
expect "text: --ci without baseline counts all as new" "$(grep -c '^  summary: [0-9]* new, 0 baselined$' "$TMP/ci_text.txt")" 1

mkdir -p "$TMP/empty"
python3 -I "$CHECK" "$TMP/empty" > /dev/null 2>&1
expect "exit 2: no pubspec.yaml" "$?" 2
python3 -I "$CHECK" "$FIX/mvn_clean" --profile nope > /dev/null 2>&1
expect "exit 2: bad --profile" "$?" 2
python3 -I "$CHECK" "$FIX/mvn_clean" --files "$TMP/does-not-exist" > /dev/null 2>&1
expect "exit 2: unreadable --files" "$?" 2
python3 -I "$CHECK" > /dev/null 2>&1
expect "exit 2: no arguments" "$?" 2

# ---------------------------------------------------------------- scale (~425 files)
BIG="$TMP/big"
mkdir -p "$BIG/lib/features"
sed 's/^name: mvn_clean/name: big_app/' "$FIX/mvn_clean/pubspec.yaml" > "$BIG/pubspec.yaml"
cp -R "$FIX/mvn_clean/lib/core" "$BIG/lib/"
i=1
while [ $i -le 25 ]; do
  cp -R "$FIX/mvn_clean/lib/features/movie" "$BIG/lib/features/movie$i"
  cp -R "$FIX/mvn_clean/lib/features/settings" "$BIG/lib/features/settings$i"
  i=$((i + 1))
done
T0=$(date +%s)
run_json big "$BIG"
T1=$(date +%s)
expect "scale: 25x2 copied features stay clean" "$(q big ids):$(q big supp)" ":50"
if [ $((T1 - T0)) -le 10 ]; then pass "scale: $(find "$BIG/lib" -name '*.dart' | wc -l | tr -d ' ') files in $((T1 - T0))s"; else fail "scale: too slow" "$((T1 - T0))s"; fi

# ---------------------------------------------------------------- speed: 500 files in < 3 s (regression: regex backtracking)
SPD="$TMP/speed"
mkdir -p "$SPD/lib/features"
printf 'name: speed\ndependencies:\n  flutter_riverpod: any\n  get_it: any\n  dio: any\n' > "$SPD/pubspec.yaml"
python3 -I - "$SPD/lib/features" <<'PY'
import os, sys
root = sys.argv[1]
blank = '\n' * 400
for i in range(100):
    d = os.path.join(root, 'f%d' % i)
    for sub in ('data', 'presentation', 'domain'):
        os.makedirs(os.path.join(d, sub), exist_ok=True)
    nxt = (i + 1) % 100
    open(os.path.join(d, 'data', 'f%d_repository.dart' % i), 'w').write(
        "import 'package:dio/dio.dart';\nimport '../../f%d/data/f%d_repository.dart';\n%s"
        "class F%dRepository {\n  F%dRepository(this._d);\n  final Dio _d;\n  Future<void> x() => _d.get('u');\n}\n"
        % (nxt, nxt, blank, i, i))
    open(os.path.join(d, 'data', 'f%d_providers.dart' % i), 'w').write(
        "import 'package:get_it/get_it.dart';\nimport 'package:flutter_riverpod/flutter_riverpod.dart';\n"
        "import 'f%d_repository.dart';\n%sfinal injector%d = GetIt.I;\n%s"
        "final f%dRepositoryProvider = Provider<F%dRepository>((ref) => injector%d<F%dRepository>());\n"
        % (i, blank, i, blank, i, i, i, i))
    open(os.path.join(d, 'domain', 'f%d.dart' % i), 'w').write('class F%d {}\n%s' % (i, blank))
    open(os.path.join(d, 'presentation', 'f%d_notifier.dart' % i), 'w').write(
        "import 'package:flutter_riverpod/flutter_riverpod.dart';\nimport '../data/f%d_providers.dart';\n"
        "import '../../f%d/presentation/f%d_page.dart';\n%s"
        "class F%dNotifier extends Notifier<int> {\n  @override\n  int build() { ref.watch(f%dRepositoryProvider); return 0; }\n}\n"
        % (i, nxt, nxt, blank, i, i))
    open(os.path.join(d, 'presentation', 'f%d_page.dart' % i), 'w').write(
        "import 'package:flutter/widgets.dart';\nimport 'f%d_notifier.dart';\n%s"
        "class F%dPage extends StatelessWidget {\n  const F%dPage({super.key});\n"
        "  @override\n  Widget build(BuildContext context) => const SizedBox();\n}\n" % (i, blank, i, i))
PY
T0=$(python3 -I -c 'import time; print(time.time())')
run_json speed "$SPD"
T1=$(python3 -I -c 'import time; print(time.time())')
SECS=$(python3 -I -c "print('%.2f' % ($T1 - $T0))")
NSPD=$(q speed nfiles)
if python3 -I -c "import sys; sys.exit(0 if $T1 - $T0 < 3 else 1)"; then pass "speed: $NSPD files in ${SECS}s (< 3s)"; else fail "speed: $NSPD files too slow" "${SECS}s"; fi
expect "speed: the 100-feature ring is one ARCH-015" "$(q speed count:ARCH-015)" 1

# ---------------------------------------------------------------- read-only
SNAP_AFTER="$(cd "$FIX" && find . -type f | sort | xargs cksum)"
expect "read-only: fixtures unchanged" "$([ "$SNAP_BEFORE" == "$SNAP_AFTER" ] && echo same || echo changed)" same

echo
echo "arch_check tests: $PASS passed, $FAIL failed"
[ $FAIL -eq 0 ] || exit 1
exit 0
