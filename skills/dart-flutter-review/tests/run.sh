#!/usr/bin/env bash
# Tests for the dart-flutter-review skill. bash 3.2 compatible, stdlib python only.
#
#   bash skills/dart-flutter-review/tests/run.sh
#
# 1. heuristics.py `grep` on tests/fixtures/smelly_app: every planted smell is
#    reported, and the known false-positive patterns (guard files) are not.
# 2. review.sh argument handling (no Dart SDK needed).
# 3. review.sh smoke test on a temp copy of the fixture: only when `dart` is on
#    PATH, otherwise SKIP. Includes the ARCHITECTURE section when the
#    flutter-architecture skill's arch_check.py is installed, otherwise SKIP.
# Prints PASS/FAIL/SKIP lines; exits 1 if anything failed. Never modifies the fixture.
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL="$(cd "$HERE/.." && pwd)"
FIX="$HERE/fixtures/smelly_app"
ARCH_CHECK="$SKILL/../flutter-architecture/scripts/arch_check.py"
fail=0
pass() { echo "PASS $*"; }
bad()  { echo "FAIL $*"; fail=1; }
skip() { echo "SKIP $*"; }

TMP="$(mktemp -d "${TMPDIR:-/tmp}/dfr-test.XXXXXX")"
trap 'rm -rf "$TMP"' EXIT
SNAP_BEFORE="$(cd "$FIX" && find . -type f | sort | xargs cksum)"

# ---- static checks ----------------------------------------------------------
python3 -I -c "import ast,sys; ast.parse(open(sys.argv[1]).read())" "$SKILL/scripts/heuristics.py" \
  && pass "heuristics.py parses" || bad "heuristics.py does not parse"
bash -n "$SKILL/scripts/review.sh" && pass "bash -n review.sh" || bad "bash -n review.sh"
bash -n "$HERE/run.sh" && pass "bash -n tests/run.sh" || bad "bash -n tests/run.sh"

# ---- 1. heuristics grep -----------------------------------------------------
(cd "$FIX" && find lib -name '*.dart' -type f | sort) > "$TMP/files"
python3 -I "$SKILL/scripts/heuristics.py" grep "$FIX" "$TMP/files" 100 1 > "$TMP/grep.txt" 2>&1 \
  && pass "heuristics grep runs" || bad "heuristics grep exited non-zero: $(head -3 "$TMP/grep.txt")"

for id in undisposed-resource swallowed-catch get-prefixed-method async-suffix \
          k-or-hungarian-prefix i-prefixed-interface noise-word-type negative-boolean \
          on-named-method widget-helper-method mediaquery-of eager-children-map \
          future-in-build opacity-widget unique-key hardcoded-color dynamic-in-api \
          then-chain grab-bag-file; do
  grep -q "\[CANDIDATE\] $id (" "$TMP/grep.txt" && pass "reports $id" || bad "missing candidate $id"
done

# specific locations that must be reported
expect() { grep -qF -- "$1" "$TMP/grep.txt" && pass "reports: $2" || bad "not reported: $2 ($1)"; }
expect '`_scroll` created, no dispose()' "undisposed ScrollController"
expect '`_poll` (subscription/timer) never cancelled' "uncancelled Timer"
expect 'catch (e) {}' "empty catch"
expect 'catch (e) { return const []; }' "catch returning a default"
expect 'void onSubmit()' "public onSubmit method"

# known false positives (fixed after real-app calibration) must stay fixed
reject() { if grep -qF -- "$1" "$TMP/grep.txt"; then bad "false positive: $2 ($(grep -F -- "$1" "$TMP/grep.txt" | head -1 | sed 's/^ *//'))"; else pass "no false positive: $2"; fi; }
reject 'ticks_provider.dart'       'tear-off release ref.onDispose(sub.cancel) / (controller.close)'
reject 'checkout_form.dart'        'for (final c in [a, b]) c.dispose() and private _onTap'
reject 'search_binding.dart'       'hand-off _out = controller;'
reject 'router.dart'               'Route<dynamic> / Map<String, dynamic> type arguments'
reject 'cart_repository_impl.dart' 'XRepositoryImpl class name'
reject 'cart_repository.dart'      'abstract interface repository contract'
reject 'main.dart'                 'plain main.dart'

# the guard files on their own must produce nothing at all
grep -Ev '(core/utils|cart_api|cart_view)\.dart$' "$TMP/files" > "$TMP/clean_files"
python3 -I "$SKILL/scripts/heuristics.py" grep "$FIX" "$TMP/clean_files" 100 1 > "$TMP/clean.txt" 2>&1
grep -q 'no heuristic candidates' "$TMP/clean.txt" \
  && pass "guard files alone: no heuristic candidates" \
  || bad "guard files alone produced candidates: $(grep CANDIDATE "$TMP/clean.txt" | head -3)"

# non-Flutter projects skip the Flutter-only heuristics
python3 -I "$SKILL/scripts/heuristics.py" grep "$FIX" "$TMP/files" 100 0 > "$TMP/dart_only.txt" 2>&1
if grep -q 'widget-helper-method\|mediaquery-of\|opacity-widget' "$TMP/dart_only.txt"; then
  bad "is_flutter=0 still reports Flutter-only heuristics"
else pass "is_flutter=0 skips Flutter-only heuristics"; fi
grep -q '\[CANDIDATE\] get-prefixed-method' "$TMP/dart_only.txt" \
  && pass "is_flutter=0 keeps Dart heuristics" || bad "is_flutter=0 lost Dart heuristics"

# ---- 1b. calibration regressions (phase-3 reports K1/K2/K3, fixtures/calib_heuristics) ----
CAL="$HERE/fixtures/calib_heuristics"
(cd "$CAL" && find lib -name '*.dart' -type f | sort) > "$TMP/cal_files"
python3 -I "$SKILL/scripts/heuristics.py" grep "$CAL" "$TMP/cal_files" 100 1 > "$TMP/cal.txt" 2>&1 \
  && pass "calib: heuristics grep runs" || bad "calib: grep exited non-zero: $(head -3 "$TMP/cal.txt")"
cexpect() { grep -qF -- "$1" "$TMP/cal.txt" && pass "calib keeps: $2" || bad "calib lost true positive: $2 ($1)"; }
creject() { if grep -qF -- "$1" "$TMP/cal.txt"; then bad "calib false positive: $2 ($(grep -F -- "$1" "$TMP/cal.txt" | head -1 | sed 's/^ *//'))"; else pass "calib no false positive: $2"; fi; }
# guards: nothing from these files except noise-word-type on HabitsManager (a different heuristic)
for g in date_tile brand app_observer ticker loaders; do creject "lib/guards/$g.dart" "guards/$g.dart reports nothing"; done
grep -F 'lib/guards/habits_manager.dart' "$TMP/cal.txt" | grep -vq 'class HabitsManager' \
  && bad "calib: habits_manager.dart reported beyond noise-word-type" || pass "calib K1 H1/H5: get*(args)/async and a file named after its class are not flagged"
creject 'getHabitsByCategory'                 'K1 H1 get* with parameters'
creject 'showDateRangePicker'                 'K1 H2 fire-and-forget .then statement in a sync callback'
creject 'HaboColors'                          'K1 H3 palette class'
creject 'Color brandGreen'                    'K1 H3 top-level const Color declaration'
creject 'void onChange'                       'K2 R1 @override BlocObserver.onChange'
creject 'buildTransitions'                    'K2 R1 @override + @protected PageRoute.buildTransitions'
creject 'void onInit'                         'K3 R4 @override GetxController.onInit'
creject '_external'                           'K3 R5 ProviderSubscription released with close()'
creject '`sub`'                               'K3 R5 ref.listen in a provider'
creject 'showRetry(future'                    'K3 R6 future: outside a FutureBuilder'
creject '_cached ??='                         'K3 R6 memoised future (??=)'
creject 'final _key = UniqueKey'              'K3 R7 UniqueKey State field'
creject 'then(delay:'                         'K3 R8 flutter_animate .then(delay:)'
# downgrades: reported, but low and under their own id
grep -q '^  \[CANDIDATE\] unique-key-outside-build (low) x2 ' "$TMP/cal.txt" \
  && pass "calib K1 H4/K2: UniqueKey outside build() is low (constructor default, helper)" || bad "calib: unique-key-outside-build: $(grep unique-key "$TMP/cal.txt" | head -2)"
grep -q '^  \[CANDIDATE\] dynamic-closure-param (low) x1 ' "$TMP/cal.txt" \
  && pass "calib K2: dynamic closure parameter is low" || bad "calib: dynamic-closure-param missing"
grep -q '^  \[CANDIDATE\] eager-children-map (low)' "$TMP/grep.txt" \
  && pass "calib K1: eager-children-map graded low" || bad "calib: eager-children-map not low"
# true positives that must survive the fixes
cexpect 'order_view.dart:13  `_note` created'  'undisposed TextEditingController'
cexpect 'String getName()'                     'zero-argument sync getName()'
cexpect 'void onTap() {}'                      'public non-override onTap()'
cexpect 'Widget _buildRow()'                   'non-override widget helper'
cexpect 'order_view.dart:32  key: UniqueKey()' 'UniqueKey in build() (medium)'
cexpect 'color: Color(0xFF123456)'             'hard-coded colour in build()'
cexpect 'order_view.dart:35  future: load()'   'FutureBuilder(future: call) in build()'
cexpect 'stream: watchTotals()'                'StreamBuilder with nested type arguments (flutter_presence)'
cexpect 'return load().then('                  '.then whose result is returned'
cexpect 'order_view.dart:24  load().then('     '.then statement inside an async function'
cexpect 'dynamic decode(dynamic raw)'          'dynamic in a public API (medium)'
cexpect 'lib/tp/string_utils.dart  grab-bag'   'utils file with several declarations'
grep -qF 'utils.dart:7  String getVersion()' "$TMP/grep.txt" && pass "smelly_app: planted zero-arg getVersion() reported" \
  || bad "smelly_app: getVersion() not reported"
grep -q 'cart_api.dart:[0-9]*  getItems().then' "$TMP/grep.txt" && bad "smelly_app: warmUp fire-and-forget .then reported" \
  || pass "smelly_app: warmUp fire-and-forget .then not reported"
grep -qF 'countItems() => getItems().then' "$TMP/grep.txt" && pass "smelly_app: arrow-body .then reported" \
  || bad "smelly_app: countItems .then not reported"

# context parsing (K1 R2 BSD sed, K2 R2 list include, K2 SDK skip), scope (K3 R3), workspace (R1)
ctx() { python3 -I "$SKILL/scripts/heuristics.py" context "$1" "${2:-3.5.0}"; }
ENVF="$HERE/fixtures/env"
rm -rf "$TMP/env"; cp -R "$ENVF" "$TMP/env"
c="$(ctx "$TMP/env/workspace/app")"
[ "$(echo "$c" | cut -f2)" = '^3.4.0-0' ] && pass "context: prerelease SDK constraint parsed verbatim (no BSD sed \\s)" \
  || bad "context: constraint '$(echo "$c" | cut -f2)'"
[ "$(echo "$c" | cut -f3)" = 'package:flutter_lints/flutter.yaml, package:bloc_lint/recommended.yaml' ] \
  && pass "context: list-form include: parsed" || bad "context: include '$(echo "$c" | cut -f3)'"
[ "$(echo "$c" | cut -f5)" = - ] && pass "context: workspace member without a resolved root has no package_config" \
  || bad "context: unexpected package_config $(echo "$c" | cut -f5)"
mkdir -p "$TMP/env/workspace/.dart_tool"
printf '{"configVersion":2,"packages":[{"name":"ws_root","rootUri":"../","packageUri":"lib/"},{"name":"ws_app","rootUri":"../app","packageUri":"lib/"}]}\n' \
  > "$TMP/env/workspace/.dart_tool/package_config.json"
c="$(ctx "$TMP/env/workspace/app")"
case "$(echo "$c" | cut -f5)" in */workspace/.dart_tool/package_config.json) pass "context: workspace member uses the root's package_config" ;;
  *) bad "context: workspace package_config '$(echo "$c" | cut -f5)'" ;; esac
echo "$c" | cut -f6 | grep -q '^pub workspace member' && pass "context: workspace note" || bad "context: no workspace note"
mkdir -p "$TMP/env/unrelated/.dart_tool" "$TMP/env/unrelated/pkg"; cp "$TMP/env/old_sdk_app/pubspec.yaml" "$TMP/env/unrelated/pkg/"
printf '{"configVersion":2,"packages":[{"name":"other","rootUri":"../other","packageUri":"lib/"}]}\n' > "$TMP/env/unrelated/.dart_tool/package_config.json"
[ "$(ctx "$TMP/env/unrelated/pkg" | cut -f5)" = - ] && pass "context: an ancestor config that doesn't list the package is ignored" \
  || bad "context: used an unrelated ancestor package_config"
[ "$(ctx "$TMP/env/old_sdk_app" | cut -f4)" != ok ] && pass "context: pre-null-safety constraint flagged for Dart 3" || bad "context: old sdk not flagged"
[ "$(ctx "$TMP/env/dart3_compat_app" | cut -f4)" = ok ] && pass "context: >=2.16.1 <3.0.0 accepted (Dart 3 reads <4.0.0)" || bad "context: dart3 compat rejected"
[ "$(ctx "$TMP/env/workspace/app" 3.3.0 | cut -f4)" != ok ] && pass "context: SDK older than ^3.4.0-0 flagged" || bad "context: older SDK not flagged"
(cd "$TMP/env/codegen_app" && find lib test -name '*.dart' | sort) > "$TMP/cg_all"
python3 -I "$SKILL/scripts/heuristics.py" scope "$TMP/env/codegen_app" "$TMP/cg_all" "" > "$TMP/cg_scope"
[ "$(tr '\n' ' ' < "$TMP/cg_scope")" = 'lib/main.dart lib/models/user.dart test/user_test.dart ' ] \
  && pass "scope fallback: *.gen.dart, GENERATED header and l10n output (arb-dir) excluded" || bad "scope fallback: $(tr '\n' ' ' < "$TMP/cg_scope")"
printf '{"files":[{"file":"lib/main.dart"}]}\n' > "$TMP/cg_arch.json"
python3 -I "$SKILL/scripts/heuristics.py" scope "$TMP/env/codegen_app" "$TMP/cg_all" "$TMP/cg_arch.json" > "$TMP/cg_scope2"
[ "$(tr '\n' ' ' < "$TMP/cg_scope2")" = 'lib/main.dart test/user_test.dart ' ] \
  && pass "scope: arch_check files[] is the source of truth for lib/" || bad "scope with files[]: $(tr '\n' ' ' < "$TMP/cg_scope2")"

# ---- 2. review.sh usage errors (exit 2, no SDK needed) ----------------------
bash "$SKILL/scripts/review.sh" >/dev/null 2>&1; rc=$?
[ "$rc" = 2 ] && pass "review.sh with no args exits 2" || bad "review.sh with no args exited $rc"
mkdir -p "$TMP/nopubspec"
bash "$SKILL/scripts/review.sh" "$TMP/nopubspec" >/dev/null 2>&1; rc=$?
[ "$rc" = 2 ] && pass "review.sh without pubspec.yaml exits 2" || bad "review.sh without pubspec.yaml exited $rc"
bash "$SKILL/scripts/review.sh" --help 2>&1 | grep -q -- '--no-arch' \
  && pass "review.sh --help documents --no-arch" || bad "review.sh --help lacks --no-arch"

# ---- 3. review.sh smoke tests (need dart) -----------------------------------
section() { awk -v h="$2" 'index($0, h) == 1 {on=1; print; next} /^== / {on=0} on' "$1"; }
if ! command -v dart >/dev/null 2>&1; then
  skip "review.sh smoke tests (dart not on PATH)"
  skip "review.sh ARCHITECTURE section (dart not on PATH)"
else
  cp -R "$FIX" "$TMP/app"
  [ -d "$FIX/.dart_tool" ] || skip "fixture has no .dart_tool: analyzer sections will be unresolved-import noise (expected)"
  bash "$SKILL/scripts/review.sh" "$TMP/app" --no-extra > "$TMP/review.txt" 2>&1; rc=$?
  [ "$rc" = 0 ] && pass "review.sh exits 0 on the fixture" || bad "review.sh exited $rc: $(tail -3 "$TMP/review.txt")"
  for h in '== CONTEXT' '== FORMAT' '== ANALYZER' '== AUTO-FIXABLE' '== ARCHITECTURE' '== CANDIDATES'; do
    grep -q "^$h" "$TMP/review.txt" && pass "review.sh prints $h" || bad "review.sh missing $h"
  done
  grep -q '\[CANDIDATE\] future-in-build' "$TMP/review.txt" \
    && pass "review.sh CANDIDATES include heuristics" || bad "review.sh CANDIDATES missing heuristics"

  if [ -f "$ARCH_CHECK" ]; then
    grep -q '^== ARCHITECTURE PROFILE' "$TMP/review.txt" \
      && pass "review.sh prints arch_check's ARCHITECTURE PROFILE" \
      || bad "review.sh did not print ARCHITECTURE PROFILE: $(grep '^== ARCHITECTURE' "$TMP/review.txt")"
    grep -q '^== ARCHITECTURE VIOLATIONS' "$TMP/review.txt" \
      && pass "review.sh prints ARCHITECTURE VIOLATIONS" || bad "review.sh missing ARCHITECTURE VIOLATIONS"
    section "$TMP/review.txt" '== ARCHITECTURE VIOLATIONS' | grep -q 'cart_view.dart' \
      && pass "architecture pass flags the planted view -> dio violation" \
      || bad "architecture pass did not flag cart_view.dart"
    bash "$SKILL/scripts/review.sh" "$TMP/app" --no-extra --profile mvn > "$TMP/review_mvn.txt" 2>&1
    grep -qi 'mvn' "$TMP/review_mvn.txt" && ! grep -q '^== ARCHITECTURE (error' "$TMP/review_mvn.txt" \
      && pass "review.sh passes --profile through" || bad "--profile passthrough failed: $(grep -A2 '^== ARCHITECTURE' "$TMP/review_mvn.txt" | head -3)"
    # diff mode passes --files: only the changed file may be reported
    if command -v git >/dev/null 2>&1; then
      (cd "$TMP/app" && git init -q && git add -A && git -c user.email=t@t -c user.name=t commit -qm init \
         && printf '\n// touched\n' >> lib/features/cart/presentation/view/checkout_form.dart)
      bash "$SKILL/scripts/review.sh" "$TMP/app" --no-extra --diff HEAD > "$TMP/review_diff.txt" 2>&1
      if ! grep -q '^== ARCHITECTURE VIOLATIONS' "$TMP/review_diff.txt"; then
        bad "diff mode: no ARCHITECTURE VIOLATIONS section ($(grep "^scope:" "$TMP/review_diff.txt"))"
      elif section "$TMP/review_diff.txt" '== ARCHITECTURE VIOLATIONS' | grep -q 'cart_view.dart'; then
        bad "diff mode: architecture pass reported a file outside the diff (--files not applied)"
      else pass "diff mode: architecture violations limited to changed files"; fi
    else skip "diff-mode architecture test (git not on PATH)"; fi
  else
    grep -q '^== ARCHITECTURE (skipped: flutter-architecture skill not installed)' "$TMP/review.txt" \
      && pass "review.sh prints the ARCHITECTURE skipped line" || bad "review.sh missing ARCHITECTURE skipped line"
    skip "review.sh ARCHITECTURE section (flutter-architecture/scripts/arch_check.py not installed yet)"
  fi

  # diff scope when the package is a sub-folder of the repo (monorepo): a modified
  # file and an untracked file must both be in scope (regression: untracked paths
  # are cwd-relative; symlinked TMPDIR paths broke the repo-prefix strip)
  if command -v git >/dev/null 2>&1; then
    mkdir -p "$TMP/mono/apps"; cp -R "$FIX" "$TMP/mono/apps/app"
    (cd "$TMP/mono" && git init -q && git add -A && git -c user.email=t@t -c user.name=t commit -qm init \
       && printf '\n// touched\n' >> apps/app/lib/main.dart && printf 'void added() {}\n' > apps/app/lib/added.dart)
    bash "$SKILL/scripts/review.sh" "$TMP/mono/apps/app" --no-extra --no-arch --diff HEAD > "$TMP/review_mono.txt" 2>&1
    grep -q '^scope: .*diff vs HEAD — 2 non-generated' "$TMP/review_mono.txt" \
      && pass "diff mode in a monorepo sub-package: modified + untracked files in scope" \
      || bad "diff mode in a monorepo sub-package: $(grep '^scope:' "$TMP/review_mono.txt")"
  else skip "monorepo diff-scope test (git not on PATH)"; fi

  bash "$SKILL/scripts/review.sh" "$TMP/app" --no-extra --no-arch > "$TMP/review_noarch.txt" 2>&1
  grep -q '^== ARCHITECTURE' "$TMP/review_noarch.txt" \
    && bad "--no-arch still printed an ARCHITECTURE section" || pass "--no-arch skips the architecture pass"

  # installed alone (no sibling skills): both optional sections degrade to a skipped line
  mkdir -p "$TMP/solo"; cp -R "$SKILL/scripts" "$TMP/solo/"
  bash "$TMP/solo/scripts/review.sh" "$TMP/app" > "$TMP/review_solo.txt" 2>&1; rc=$?
  [ "$rc" = 0 ] && pass "review.sh without sibling skills exits 0" || bad "review.sh without siblings exited $rc"
  grep -q '^== ARCHITECTURE (skipped: flutter-architecture skill not installed)' "$TMP/review_solo.txt" \
    && pass "without siblings: ARCHITECTURE skipped line" || bad "without siblings: no ARCHITECTURE skipped line"
  grep -q '^== EXTRA LINTS (skipped:' "$TMP/review_solo.txt" \
    && pass "without siblings: EXTRA LINTS skipped line" || bad "without siblings: no EXTRA LINTS skipped line"
fi

# ---- 4. CI mode + sibling passes (stub `dart`, stub sibling skills; no SDK needed) ----
# A fake suite: the real review + architecture scripts next to stub test_gaps.py / check_errors.py
# that echo the arguments they got, and a stub `dart` whose analyzer output is controlled by a file.
SUITE="$TMP/suite"
mkdir -p "$SUITE/dart-flutter-review" "$SUITE/flutter-architecture" "$SUITE/flutter-testing/scripts" \
         "$SUITE/flutter-error-handling/scripts" "$TMP/bin"
cp -R "$SKILL/scripts" "$SUITE/dart-flutter-review/"
[ -f "$ARCH_CHECK" ] && cp -R "$SKILL/../flutter-architecture/scripts" "$SUITE/flutter-architecture/"
cat > "$SUITE/flutter-testing/scripts/test_gaps.py" <<'PY'
import sys
print('== TEST GAPS')
print('  args: ' + ' '.join(sys.argv[2:]))
print('  [TEST-untested-repository] (high) x1 — Repository has no test.')
print('      lib/features/cart/data/repositories/cart_repository_impl.dart:1  CartRepositoryImpl')
print('')
print('== TEST SMELLS')
print('  none')
PY
cat > "$SUITE/flutter-error-handling/scripts/check_errors.py" <<'PY'
import sys
if '--files' in sys.argv:
    print('  files: ' + ','.join(l.strip() for l in open(sys.argv[sys.argv.index('--files') + 1]) if l.strip()))
print('  args: ' + ' '.join(a for a in sys.argv[2:] if not a.startswith('/')))
print('  [ERR-001] swallowed-catch (high) x2 — A catch discards the error.')
print('      lib/features/cart/data/sources/cart_api.dart:23  catch (e) { return const []; }')
PY
# stub §14/§17 checkers (secure defaults, navigation, forms, i18n): echo args, one group each
for pair in flutter-secure-defaults:check_secure_defaults:SECURITY\ DEFAULTS:SEC-001 flutter-navigation:check_navigation:NAVIGATION:NAV-003 \
            flutter-forms:check_forms:FORMS:FORM-001 flutter-i18n:check_i18n:I18N:I18N-010 \
            flutter-performance:check_performance:PERFORMANCE:PERF-001 flutter-persistence:check_persistence:PERSISTENCE:PERSIST-001 flutter-networking:check_networking:NETWORKING:NET-001 flutter-firebase:check_firebase:FIREBASE:FIRE-001 flutter-platform-integration:check_platform:PLATFORM:PLAT-001 \
            flutter-design-system:check_design_system:DESIGN\ SYSTEM:DS-001 flutter-adaptive-layout:check_adaptive:ADAPTIVE\ LAYOUT:ADAPT-001 flutter-accessibility:check_accessibility:ACCESSIBILITY:A11Y-001 \
            flutter-release:check_release:RELEASE:REL-001; do
  sk="${pair%%:*}"; rest="${pair#*:}"; nm="${rest%%:*}"; rest="${rest#*:}"; hd="${rest%%:*}"; rid="${rest#*:}"
  mkdir -p "$SUITE/$sk/scripts"
  cat > "$SUITE/$sk/scripts/$nm.py" <<PY
import sys
print('== $hd')
if '--files' in sys.argv:
    print('  files: ' + ','.join(l.strip() for l in open(sys.argv[sys.argv.index('--files') + 1]) if l.strip()))
print('  args: ' + ' '.join(a for a in sys.argv[2:] if not a.startswith('/')))
print('  [$rid] stub-rule (medium) x1 — stub finding.')
print('      lib/main.dart:1  stub')
PY
done
# stub flutter-security-audit scan.sh: --json, exit 1 (its own CI gate fires on CRITICAL/HIGH)
mkdir -p "$SUITE/flutter-security-audit"
cat > "$SUITE/flutter-security-audit/scan.sh" <<'SH'
#!/usr/bin/env bash
root="$1"; [ "$2" = --json ] || { echo "stub wants --json" >&2; exit 2; }
cat <<JSON
{ "tool": "flutter-security-audit", "findings": [
  { "severity": "CRITICAL", "id": "NET-ACCEPT-ALL", "masvs": "MASVS-NETWORK", "cwe": "CWE-295", "location": "$root/lib/features/cart/data/sources/cart_api.dart:12", "evidence": "badCertificateCallback = (c, h, p) => true" },
  { "severity": "HIGH", "id": "NET-NO-PINNING", "masvs": "MASVS-NETWORK", "cwe": "CWE-295", "location": "(project-wide)", "evidence": "MISSING: no certificate pinning" },
  { "severity": "LOW", "id": "COD-DEBUG-PRINT", "masvs": "MASVS-CODE", "cwe": "CWE-489", "location": "$root/lib/main.dart:3", "evidence": "print(x)" }
], "count": 3 }
JSON
exit 1
SH
cat > "$TMP/bin/dart" <<'SH'
#!/usr/bin/env bash
[ -n "${STUB_LOG:-}" ] && echo "$*" >> "$STUB_LOG"
case "$1" in
  --version) echo "Dart SDK version: 3.5.0 (stable) (stub)" ;;
  analyze) [ -f "${STUB_ANALYZE:-/nonexistent}" ] && cat "$STUB_ANALYZE" || echo "No issues found!" ;;
  fix) echo "Nothing to fix!" ;;
  *) : ;;
esac
exit 0
SH
chmod +x "$TMP/bin/dart"
RV="$SUITE/dart-flutter-review/scripts/review.sh"
rm -rf "$TMP/ciapp"; cp -R "$FIX" "$TMP/ciapp"
mkdir -p "$TMP/ciapp/.dart_tool" && echo '{}' > "$TMP/ciapp/.dart_tool/package_config.json"
srun() { PATH="$TMP/bin:$PATH" bash "$RV" "$TMP/ciapp" --no-extra "$@"; }

srun > "$TMP/s_plain.txt" 2>&1; rc=$?
[ "$rc" = 0 ] && pass "stub: review.sh (no --ci) exits 0 despite findings" || bad "stub: review.sh exited $rc"
grep -q '^== TEST GAPS$' "$TMP/s_plain.txt" && grep -q '^== TEST SMELLS$' "$TMP/s_plain.txt" \
  && pass "TEST GAPS section printed from the sibling" || bad "TEST GAPS section missing"
grep -q '^== ERROR HANDLING$' "$TMP/s_plain.txt" \
  && pass "ERROR HANDLING header added when the sibling prints none" || bad "ERROR HANDLING header missing"
grep -q '^  args: --max 5$' "$TMP/s_plain.txt" && pass "siblings get --max" || bad "siblings args: $(grep '  args:' "$TMP/s_plain.txt")"
grep -q '^  \[CANDIDATE\] swallowed-catch (high) x2 — see ERROR HANDLING' "$TMP/s_plain.txt" \
  && pass "swallowed-catch defers to ERROR HANDLING (count kept, locations dropped)" || bad "swallowed-catch not deferred"
section "$TMP/s_plain.txt" '== CANDIDATES' | grep -q 'cart_api.dart:32  catch' \
  && bad "deferred swallowed-catch still lists locations" || pass "deferred swallowed-catch lists no locations"
grep -q '^== CI RESULT' "$TMP/s_plain.txt" && bad "CI RESULT printed without --ci" || pass "no CI RESULT without --ci"

srun --profile mvn --no-tests > "$TMP/s_prof.txt" 2>&1
section "$TMP/s_prof.txt" '== ERROR HANDLING' | grep -q '^  args: --max 5 --profile mvn$' \
  && pass "--profile passed to check_errors" || bad "--profile not passed: $(grep '  args:' "$TMP/s_prof.txt")"
grep -q '^== TEST GAPS' "$TMP/s_prof.txt" && bad "--no-tests still printed TEST GAPS" || pass "--no-tests skips TEST GAPS"
srun --no-errors > "$TMP/s_noerr.txt" 2>&1
grep -q '^== ERROR HANDLING' "$TMP/s_noerr.txt" && bad "--no-errors still printed ERROR HANDLING" || pass "--no-errors skips ERROR HANDLING"
grep -q 'cart_api.dart:32  catch (e) {}' "$TMP/s_noerr.txt" \
  && pass "--no-errors: swallowed-catch keeps its locations" || bad "--no-errors: swallowed-catch lost its locations"

# siblings missing: graceful skip lines
mkdir -p "$TMP/suite_min/dart-flutter-review"; cp -R "$SKILL/scripts" "$TMP/suite_min/dart-flutter-review/"
PATH="$TMP/bin:$PATH" bash "$TMP/suite_min/dart-flutter-review/scripts/review.sh" "$TMP/ciapp" --no-extra > "$TMP/s_min.txt" 2>&1; rc=$?
[ "$rc" = 0 ] && grep -q '^== TEST GAPS (skipped: flutter-testing skill not installed)$' "$TMP/s_min.txt" \
  && grep -q '^== ERROR HANDLING (skipped: flutter-error-handling skill not installed)$' "$TMP/s_min.txt" \
  && pass "missing siblings: TEST GAPS / ERROR HANDLING skipped lines, exit 0" || bad "missing siblings: rc=$rc $(grep '^== ' "$TMP/s_min.txt" | tr '\n' ' ')"
# a crashing sibling is reported, not fatal
printf 'import sys\nsys.exit("boom")\n' > "$TMP/suite_min/crash.py"
mkdir -p "$TMP/suite_min/flutter-testing/scripts"; cp "$TMP/suite_min/crash.py" "$TMP/suite_min/flutter-testing/scripts/test_gaps.py"
PATH="$TMP/bin:$PATH" bash "$TMP/suite_min/dart-flutter-review/scripts/review.sh" "$TMP/ciapp" --no-extra > "$TMP/s_crash.txt" 2>&1; rc=$?
[ "$rc" = 0 ] && grep -q '^== TEST GAPS (error: test_gaps.py exited 1)$' "$TMP/s_crash.txt" \
  && pass "crashing sibling: error line, run continues" || bad "crashing sibling: rc=$rc"

# ---- 4a. Part B: secure-defaults / security-audit / navigation / forms / i18n sections ----
for h in 'SECURITY DEFAULTS' 'NAVIGATION' 'FORMS' 'I18N' 'PERFORMANCE' 'PERSISTENCE' 'NETWORKING' 'FIREBASE' 'PLATFORM' 'DESIGN SYSTEM' 'ADAPTIVE LAYOUT' 'ACCESSIBILITY' 'RELEASE'; do
  section "$TMP/s_plain.txt" "== $h" | grep -q '^  args: --max 5$' && pass "$h: checker runs with --max" \
    || bad "$h: $(section "$TMP/s_plain.txt" "== $h" | head -3 | tr '\n' ' ')"
done
section "$TMP/s_prof.txt" '== NAVIGATION' | grep -q '^  args: --max 5 --profile mvn$' \
  && pass "checkers get --profile" || bad "checkers --profile: $(section "$TMP/s_prof.txt" '== NAVIGATION' | head -3 | tr '\n' ' ')"
sa="$(section "$TMP/s_plain.txt" '== SECURITY AUDIT')"
echo "$sa" | head -1 | grep -q 'never fails CI' && echo "$sa" | grep -q '^  \[NET-ACCEPT-ALL\] (high) x1 — CRITICAL; MASVS-NETWORK · CWE-295 (pattern)$' \
  && echo "$sa" | grep -q '^      lib/features/cart/data/sources/cart_api.dart:12  badCertificateCallback' \
  && echo "$sa" | grep -q '^  \[NET-NO-PINNING\] (high) x1 — MASVS-NETWORK · CWE-295 (absence check)$' \
  && pass "SECURITY AUDIT: scan.sh --json regrouped (critical->high, root-relative paths, absence checks marked)" \
  || bad "SECURITY AUDIT section: $(echo "$sa" | head -6 | tr '\n' ' ')"
grep -q '^== SECURITY DEFAULTS\|^== NAVIGATION\|^== FORMS\|^== I18N\|^== SECURITY AUDIT' "$TMP/s_min.txt" \
  && ! grep -q '(skipped' "$TMP/s_min.txt" && bad "missing checkers printed sections" || true
ok=1
for kv in "SECURITY DEFAULTS:flutter-secure-defaults" "SECURITY AUDIT:flutter-security-audit" "NAVIGATION:flutter-navigation" "FORMS:flutter-forms" "I18N:flutter-i18n" \
          "PERFORMANCE:flutter-performance" "PERSISTENCE:flutter-persistence" "NETWORKING:flutter-networking" "FIREBASE:flutter-firebase" "PLATFORM:flutter-platform-integration" "DESIGN SYSTEM:flutter-design-system" "ADAPTIVE LAYOUT:flutter-adaptive-layout" "ACCESSIBILITY:flutter-accessibility" "RELEASE:flutter-release"; do
  grep -q "^== ${kv%%:*} (skipped: ${kv#*:} skill not installed)$" "$TMP/s_min.txt" || { ok=0; bad "missing ${kv#*:}: no skipped line"; }
done
[ $ok = 1 ] && pass "missing checkers: one skipped line each, exit 0"
srun --no-security > "$TMP/s_nosec.txt" 2>&1
grep -q '^== SECURITY' "$TMP/s_nosec.txt" && bad "--no-security printed a SECURITY section" || pass "--no-security skips SECURITY DEFAULTS and SECURITY AUDIT"
srun --no-audit --no-nav > "$TMP/s_noaud.txt" 2>&1
grep -q '^== SECURITY DEFAULTS' "$TMP/s_noaud.txt" && ! grep -q '^== SECURITY AUDIT' "$TMP/s_noaud.txt" \
  && ! grep -q '^== NAVIGATION' "$TMP/s_noaud.txt" && pass "--no-audit / --no-nav skip only their section" || bad "--no-audit/--no-nav"
srun --skip forms,i18n,tests > "$TMP/s_skip.txt" 2>&1
! grep -q '^== FORMS\|^== I18N\|^== TEST GAPS' "$TMP/s_skip.txt" && grep -q '^== NAVIGATION' "$TMP/s_skip.txt" \
  && pass "--skip forms,i18n,tests" || bad "--skip: $(grep '^== ' "$TMP/s_skip.txt" | tr '\n' ' ')"
srun --skip bogus > /dev/null 2>&1; rc=$?
[ "$rc" = 2 ] && pass "--skip with an unknown section exits 2" || bad "--skip bogus exited $rc"
FLUTTER_SECURITY_AUDIT_SCAN="$SUITE/flutter-security-audit/scan.sh" PATH="$TMP/bin:$PATH" \
  bash "$TMP/suite_min/dart-flutter-review/scripts/review.sh" "$TMP/ciapp" --no-extra --ci > "$TMP/s_env.txt" 2>&1; rc=$?
grep -q '^== SECURITY AUDIT (flutter-security-audit scan.sh' "$TMP/s_env.txt" && [ "$rc" != 2 ] \
  && ! grep -q '^  architecture: FAIL\|^  analyzer: FAIL' "$TMP/s_env.txt" && [ "$rc" = 0 ] \
  && pass "\$FLUTTER_SECURITY_AUDIT_SCAN override; scan.sh exit 1 never fails --ci" || bad "audit env override: rc=$rc $(grep -A4 '^== CI RESULT' "$TMP/s_env.txt" | tr '\n' ' ')"
bash "$RV" --help 2>&1 | grep -q -- '--no-i18n' && bash "$RV" --help 2>&1 | grep -q -- '--skip <list>' \
  && pass "--help documents the new flags" || bad "--help lacks the new flags"

# ---- 4b. v1.1 checkers: performance / persistence / design system / accessibility (CONTRACTS §25) ----
order="$(grep -E '^== (I18N|PERFORMANCE|PERSISTENCE|NETWORKING|FIREBASE|PLATFORM|DESIGN SYSTEM|ADAPTIVE LAYOUT|ACCESSIBILITY|RELEASE|CANDIDATES)' "$TMP/s_plain.txt" | sed 's/^== //; s/ (.*//' | tr '\n' ',')"
[ "$order" = "I18N,PERFORMANCE,PERSISTENCE,NETWORKING,FIREBASE,PLATFORM,DESIGN SYSTEM,ADAPTIVE LAYOUT,ACCESSIBILITY,RELEASE,CANDIDATES," ] \
  && pass "v1.1 sections run after I18N, in contract order" || bad "v1.1 section order: $order"
cand="$(section "$TMP/s_plain.txt" '== CANDIDATES')"
echo "$cand" | grep -q '^  \[CANDIDATE\] eager-children-map (low) x1 — see PERFORMANCE' \
  && echo "$cand" | grep -q '^      lib/features/cart/presentation/view/cart_view.dart:40  return Opacity' \
  && echo "$cand" | grep -q '^  \[CANDIDATE\] hardcoded-color (low) x1 — see DESIGN SYSTEM' \
  && pass "eager-children-map defers to PERFORMANCE, hardcoded-color to DESIGN SYSTEM; static Opacity keeps its location" \
  || bad "deferral: $(echo "$cand" | grep -E 'eager|opacity|hardcoded' | tr '\n' ' ')"
echo "$cand" | grep -q 'cart_view.dart:49\|cart_view.dart:60' \
  && bad "deferred heuristics still list locations" || pass "deferred heuristics list no locations"
srun --no-perf --no-ds > "$TMP/s_noperf.txt" 2>&1
! grep -q '^== PERFORMANCE\|^== DESIGN SYSTEM' "$TMP/s_noperf.txt" && grep -q '^== PERSISTENCE' "$TMP/s_noperf.txt" \
  && section "$TMP/s_noperf.txt" '== CANDIDATES' | grep -q 'cart_view.dart:49  color: Color(0xFF00897B)' \
  && section "$TMP/s_noperf.txt" '== CANDIDATES' | grep -q 'cart_view.dart:60' \
  && pass "--no-perf / --no-ds: sections skipped, heuristics keep their locations" || bad "--no-perf/--no-ds: $(grep '^== ' "$TMP/s_noperf.txt" | tr '\n' ' ')"
srun --skip persist,a11y,net,release,platform,adaptive,firebase > "$TMP/s_skip2.txt" 2>&1
! grep -q '^== PERSISTENCE\|^== ACCESSIBILITY\|^== NETWORKING\|^== RELEASE\|^== PLATFORM\|^== ADAPTIVE\|^== FIREBASE' "$TMP/s_skip2.txt" && grep -q '^== PERFORMANCE' "$TMP/s_skip2.txt" \
  && pass "--skip persist,a11y" || bad "--skip persist,a11y: $(grep '^== ' "$TMP/s_skip2.txt" | tr '\n' ' ')"
section "$TMP/s_prof.txt" '== ACCESSIBILITY' | grep -q '^  args: --max 5 --profile mvn$' \
  && pass "v1.1 checkers get --profile" || bad "v1.1 --profile: $(section "$TMP/s_prof.txt" '== ACCESSIBILITY' | head -3 | tr '\n' ' ')"
bash "$RV" --help 2>&1 | grep -q -- '--no-a11y' && pass "--help documents the v1.1 flags" || bad "--help lacks --no-a11y"

# ---- 4b2. PASS PLAN: which judgment passes have work ------------------------
P="$TMP/plan_sec"; rm -rf "$P"; mkdir -p "$P"
printf '== ERROR HANDLING\n  [ERR-001] swallowed-catch (high) x2 — d.\n      lib/a.dart:1  x\n' > "$P/errors.txt"
printf '== NAVIGATION\n  no navigation findings\n' > "$P/nav.txt"
printf '== DESIGN SYSTEM\n  [DS-001] raw-color-in-widget (info) x1 — d.\n' > "$P/ds.txt"
printf '== FIREBASE (skipped: flutter-firebase skill not installed)\n' > "$P/firebase.txt"
printf '== PERFORMANCE (error: check_performance.py exited 1)\n' > "$P/perf.txt"
python3 -I "$SKILL/scripts/heuristics.py" plan "$P" 8 > "$TMP/plan.txt" 2>&1
grep -q '^  run:  F errors: 1 group(s) to confirm (ERR-001)$' "$TMP/plan.txt" \
  && grep -q '^  skip: G navigation: no findings at low or above$' "$TMP/plan.txt" \
  && grep -q '^  skip: L design system: no findings at low or above$' "$TMP/plan.txt" \
  && grep -q '^  skip: R firebase: skill not installed$' "$TMP/plan.txt" \
  && grep -q '^  run:  J performance: the checker failed' "$TMP/plan.txt" \
  && grep -q '^  skip: E testing: not run (switched off)$' "$TMP/plan.txt" \
  && grep -q '^  mode: quick (8 file(s) <= 15)' "$TMP/plan.txt" \
  && pass "PASS PLAN: run with findings, skip empty/info-only/missing, error means read it, quick mode" \
  || bad "PASS PLAN: $(tr '\n' '|' < "$TMP/plan.txt")"
python3 -I "$SKILL/scripts/heuristics.py" plan "$P" 40 | grep -q '^  mode: parallel' \
  && pass "PASS PLAN: parallel mode above 15 files" || bad "PASS PLAN: no parallel mode for 40 files"
grep -q '^== PASS PLAN' "$TMP/s_plain.txt" && section "$TMP/s_plain.txt" '== PASS PLAN' | grep -q '^  run:  F errors' \
  && pass "review.sh prints the PASS PLAN after CANDIDATES" || bad "review.sh: no PASS PLAN section"

# ---- 4b3. --findings-only: one compact answer for an agent checking its own change --
srun --findings-only > "$TMP/s_fo.txt" 2>&1; rc=$?
head -1 "$TMP/s_fo.txt" | grep -q '^== FINDINGS (' && grep -q '^  \[ERR-001\] swallowed-catch (high) x2' "$TMP/s_fo.txt" \
  && grep -q '^  \[NAV-003\]' "$TMP/s_fo.txt" && ! grep -q '^== CANDIDATES\|^== TEST GAPS\|^== CONTEXT\|^== PASS PLAN\|\[CANDIDATE\]' "$TMP/s_fo.txt" \
  && [ "$rc" = 0 ] && pass "--findings-only: checker groups only, no candidates/test gaps/context, exit 0" \
  || bad "--findings-only: rc=$rc $(head -6 "$TMP/s_fo.txt" | tr '\n' '|')"
[ "$(wc -l < "$TMP/s_fo.txt" | tr -d ' ')" -lt "$(wc -l < "$TMP/s_plain.txt" | tr -d ' ')" ] \
  && pass "--findings-only is shorter than the full report" || bad "--findings-only is not shorter"
printf '== DESIGN SYSTEM\n  [DS-001] raw-color-in-widget (info) x1 — d.\n      lib/a.dart:1  x\n== FORMS\n  no form findings\n' > "$TMP/fo_in.txt"
python3 -I "$SKILL/scripts/heuristics.py" compact "$TMP/fo_in.txt" | grep -q '^== FINDINGS: none at low or above' \
  && pass "--findings-only: info-only and empty sections read as nothing to fix" || bad "compact: info-only not treated as clean"

# ---- 4c. environment fixes on fixtures/env (stub dart 3.5.0) ----------------
erun() { d="$1"; shift; PATH="$TMP/bin:$PATH" bash "$TMP/suite_min/dart-flutter-review/scripts/review.sh" "$d" "$@"; }
rm -rf "$TMP/suite_min/flutter-testing"   # leave only review (+ the hub's lint set for EXTRA LINTS)
mkdir -p "$TMP/suite_min/dart-flutter-best-practices/assets"
cp "$SKILL/../dart-flutter-best-practices/assets/analysis_options.yaml" "$TMP/suite_min/dart-flutter-best-practices/assets/" 2>/dev/null \
  || printf 'linter:\n  rules:\n    - prefer_final_locals\n' > "$TMP/suite_min/dart-flutter-best-practices/assets/analysis_options.yaml"
: > "$TMP/stub.log"
STUB_LOG="$TMP/stub.log" erun "$TMP/env/workspace/app" --ci > "$TMP/e_ws.txt" 2>&1; rc=$?
grep -q 'WARNING: no .dart_tool' "$TMP/e_ws.txt" && bad "workspace member: false pub-get warning" || pass "K1/K3 R1: workspace member, no false pub-get warning"
grep -q '^packages:       pub workspace member' "$TMP/e_ws.txt" && pass "workspace member: CONTEXT says where packages resolve" || bad "workspace: no packages line"
grep -q '^== EXTRA LINTS (Effective Dart' "$TMP/e_ws.txt" && pass "workspace member: EXTRA LINTS runs" || bad "workspace: EXTRA LINTS $(grep '^== EXTRA' "$TMP/e_ws.txt")"
grep -q -- "--packages=.*/workspace/.dart_tool/package_config.json" "$TMP/stub.log" \
  && pass "workspace member: EXTRA LINTS gets the workspace root's --packages" || bad "workspace: --packages not passed ($(grep packages "$TMP/stub.log"))"
grep -q '^  analyzer: pass (0 errors in scope)$' "$TMP/e_ws.txt" && [ "$rc" = 0 ] \
  && pass "workspace member: CI counts the analyzer (packages resolved)" || bad "workspace CI: rc=$rc $(grep '  analyzer:' "$TMP/e_ws.txt")"
grep -q '^dart sdk:       3.5.0   pubspec constraint: \^3.4.0-0$' "$TMP/e_ws.txt" \
  && pass "K1 R2: CONTEXT constraint clean on bash 3.2/BSD tools" || bad "CONTEXT constraint: $(grep '^dart sdk' "$TMP/e_ws.txt")"
grep -q '^lint include:   package:flutter_lints/flutter.yaml, package:bloc_lint/recommended.yaml$' "$TMP/e_ws.txt" \
  && pass "K2 R2: CONTEXT shows a list-form include" || bad "CONTEXT include: $(grep '^lint include' "$TMP/e_ws.txt")"
rm -f "$TMP/env/workspace/.dart_tool/package_config.json"
erun "$TMP/env/workspace/app" > "$TMP/e_ws2.txt" 2>&1
grep -q 'WARNING: no .dart_tool/package_config.json (here or in a pub workspace root)' "$TMP/e_ws2.txt" \
  && grep -q '^== EXTRA LINTS (skipped: packages not resolved' "$TMP/e_ws2.txt" \
  && pass "unresolved workspace: warning + EXTRA LINTS skip line (never silently vanishes)" || bad "unresolved workspace: $(grep 'WARNING\|EXTRA' "$TMP/e_ws2.txt" | tr '\n' ' ')"

erun "$TMP/env/old_sdk_app" --ci > "$TMP/e_old.txt" 2>&1; rc=$?
grep -q '^== ANALYZER (skipped: pubspec sdk constraint >=2.7.0 <3.0.0 is pre-null-safety' "$TMP/e_old.txt" \
  && grep -q '^== AUTO-FIXABLE (skipped:' "$TMP/e_old.txt" && grep -q '^  analyzer: not counted (skipped:' "$TMP/e_old.txt" && [ "$rc" = 0 ] \
  && pass "K2: SDK constraint excludes the installed SDK -> analyzer skipped with a clear line, not counted" || bad "old sdk: rc=$rc $(grep '^== ANALYZER\|analyzer:' "$TMP/e_old.txt" | tr '\n' ' ')"
erun "$TMP/env/dart3_compat_app" > "$TMP/e_d3.txt" 2>&1
grep -q '^== ANALYZER (project' "$TMP/e_d3.txt" && pass "K2: >=2.16.1 <3.0.0 still analysed on Dart 3" || bad "dart3 compat: $(grep '^== ANALYZER' "$TMP/e_d3.txt")"

CG="$TMP/env/codegen_app"; mkdir -p "$CG/.dart_tool"; echo '{}' > "$CG/.dart_tool/package_config.json"
{ printf 'ERROR|COMPILE_TIME_ERROR|URI_HAS_NOT_BEEN_GENERATED|%s|3|6|18|Target of URI hasn'"'"'t been generated: '"'"'user.freezed.dart'"'"'.
' "$CG/lib/models/user.dart"
  for i in 1 2 3 4 5 6; do printf 'ERROR|COMPILE_TIME_ERROR|UNDEFINED_IDENTIFIER|%s|5|%s|4|Undefined name '"'"'_$UserFromJson'"'"'.
' "$CG/lib/models/user.dart" "$i"; done
  printf 'ERROR|COMPILE_TIME_ERROR|MIXIN_OF_NON_CLASS|%s|7|1|5|Classes can only mix in mixins and classes.
' "$CG/lib/models/user.dart"
  printf 'ERROR|COMPILE_TIME_ERROR|UNDEFINED_GETTER|%s|5|14|4|The getter '"'"'name'"'"' isn'"'"'t defined for the type '"'"'User'"'"'.
' "$CG/lib/main.dart"
  printf 'ERROR|COMPILE_TIME_ERROR|UNDEFINED_IDENTIFIER|%s|1|1|4|Undefined name x.
' "$CG/lib/gen/assets.gen.dart"; } > "$TMP/cg.an"
STUB_ANALYZE="$TMP/cg.an" erun "$CG" --ci > "$TMP/e_cg.txt" 2>&1; rc=$?
grep -q '^scope:          whole project — 3 non-generated .dart files$' "$TMP/e_cg.txt" \
  && pass "K3 R3: *.gen.dart, GENERATED header and l10n output out of scope" || bad "codegen scope: $(grep '^scope' "$TMP/e_cg.txt")"
grep -q '^  codegen: 2 generated file(s) missing' "$TMP/e_cg.txt" \
  && grep -q '^  collapsed: 9 error(s) are likely codegen cascades, not counted in CI' "$TMP/e_cg.txt" \
  && pass "K3 R2: missing codegen detected, cascades collapsed into one line" || bad "codegen: $(grep 'codegen\|collapsed' "$TMP/e_cg.txt" | tr '\n' ' ')"
grep -q '^  ERROR   undefined_identifier' "$TMP/e_cg.txt" && bad "codegen: cascade errors still listed one by one" || pass "codegen: cascade errors not listed individually"
[ "$rc" = 0 ] && grep -q '^  analyzer: pass (0 errors in scope; 9 likely codegen-cascade' "$TMP/e_cg.txt" \
  && pass "K3 R2: codegen cascades don't fail --ci" || bad "codegen CI: rc=$rc $(grep '  analyzer:' "$TMP/e_cg.txt")"
printf 'ERROR|SYNTACTIC_ERROR|EXPECTED_TOKEN|%s|4|1|1|Expected to find '"'"';'"'"'.
' "$CG/lib/main.dart" >> "$TMP/cg.an"
STUB_ANALYZE="$TMP/cg.an" erun "$CG" --ci > "$TMP/e_cg2.txt" 2>&1; rc=$?
[ "$rc" = 1 ] && grep -q '^  analyzer: FAIL — 1 error(s) in scope; 9 likely codegen-cascade' "$TMP/e_cg2.txt" \
  && pass "codegen: a real (non-cascade) error still fails --ci" || bad "codegen real error: rc=$rc $(grep '  analyzer:' "$TMP/e_cg2.txt")"
printf 'An unexpected error was encountered by the Analysis Server.\nPlease file an issue at https://github.com/dart-lang/sdk/issues\n\nNull check operator used on a null value\n#0      GenericName.registerNodeProcessors (package:internal_lint/src/lints/generic_name.dart:30)\n#1      PluginServer._computeDiagnosticsFromPlugin (package:analysis_server_plugin/src/plugin_server.dart:586)\n' > "$TMP/crash.an"
mkdir -p "$TMP/env/dart3_compat_app/.dart_tool"; echo '{}' > "$TMP/env/dart3_compat_app/.dart_tool/package_config.json"
STUB_ANALYZE="$TMP/crash.an" erun "$TMP/env/dart3_compat_app" --ci > "$TMP/e_crash.txt" 2>&1; rc=$?
an="$(section "$TMP/e_crash.txt" '== ANALYZER')"
[ "$(echo "$an" | grep -c .)" = 2 ] && echo "$an" | grep -q '^  analyzer crashed (An unexpected error was encountered by the Analysis Server: Null check operator used on a null value; in analyzer plugin package:internal_lint)' \
  && ! echo "$an" | grep -q '#0' && [ "$rc" = 0 ] && grep -q '^  analyzer: not counted (the analyzer crashed' "$TMP/e_crash.txt" \
  && pass "K3 R9: analyzer crash is one status line, not a stack dump, and not counted" || bad "crash: rc=$rc $(echo "$an" | head -4 | tr '\n' ' ')"

# diff mode: check_errors gets --files with the changed files
if command -v git >/dev/null 2>&1; then
  (cd "$TMP/ciapp" && git init -q && git add -A && git -c user.email=t@t -c user.name=t commit -qm init \
     && printf '\n// touched\n' >> lib/features/cart/data/sources/cart_api.dart)
  srun --diff HEAD > "$TMP/s_diff.txt" 2>&1
  grep -q '^  files: lib/features/cart/data/sources/cart_api.dart$' "$TMP/s_diff.txt" \
    && pass "diff mode: check_errors gets --files" || bad "diff mode: check_errors files: $(grep '  files:' "$TMP/s_diff.txt")"
  section "$TMP/s_diff.txt" '== TEST GAPS' | grep -q '^  note: whole project' \
    && pass "diff mode: TEST GAPS notes its whole-project scope" || bad "diff mode: no TEST GAPS scope note"
  section "$TMP/s_diff.txt" '== NAVIGATION' | grep -q '^  files: lib/features/cart/data/sources/cart_api.dart$' \
    && section "$TMP/s_diff.txt" '== I18N' | grep -q '^  args: --max 5 --files$' \
    && pass "diff mode: §14/§17 checkers get --files" || bad "diff mode: checker files: $(section "$TMP/s_diff.txt" '== NAVIGATION' | head -3 | tr '\n' ' ')"
  fb="$(section "$TMP/s_diff.txt" '== FIREBASE')"
  echo "$fb" | grep -q '^  note: whole project' && ! echo "$fb" | grep -q '^  files:' \
    && pass "diff mode: FIREBASE runs whole-project (no --files) and says so" || bad "diff mode firebase: $(echo "$fb" | head -4 | tr '\n' ' ')"
  rl="$(section "$TMP/s_diff.txt" '== RELEASE')"
  echo "$rl" | grep -q '^  note: whole project' && echo "$rl" | grep -q '^  args: --max 5$' && ! echo "$rl" | grep -q '^  files:' \
    && pass "diff mode: RELEASE runs whole-project (no --files) and says so" || bad "diff mode release: $(echo "$rl" | head -4 | tr '\n' ' ')"
  sd="$(section "$TMP/s_diff.txt" '== SECURITY AUDIT')"
  echo "$sd" | grep -q 'NET-ACCEPT-ALL' && ! echo "$sd" | grep -q 'NET-NO-PINNING\|COD-DEBUG-PRINT' \
    && echo "$sd" | grep -q '^  diff mode: 2 hit(s) outside the changed files or project-wide omitted' \
    && pass "diff mode: SECURITY AUDIT keeps only hits in changed files" || bad "diff mode audit: $(echo "$sd" | tr '\n' ' ')"
else skip "diff-mode sibling tests (git not on PATH)"; fi

# CI exit policy + $GITHUB_STEP_SUMMARY
for bad_args in "--fail-on info" "--fail-on" "--baseline $TMP/nope.json" "--bogus"; do
  srun --ci $bad_args > /dev/null 2>&1; rc=$?
  [ "$rc" = 2 ] && pass "usage error exits 2: --ci $bad_args" || bad "--ci $bad_args exited $rc"
done
if [ -f "$ARCH_CHECK" ]; then
  : > "$TMP/summary.md"
  GITHUB_STEP_SUMMARY="$TMP/summary.md" srun --ci > "$TMP/s_ci.txt" 2>&1; rc=$?
  [ "$rc" = 1 ] && grep -q '^  architecture: FAIL — 2 new at or above high$' "$TMP/s_ci.txt" \
    && pass "--ci: new high architecture violations exit 1" || bad "--ci: rc=$rc $(grep -A5 '^== CI RESULT' "$TMP/s_ci.txt" | tr '\n' ' ')"
  grep -q '^  result: FAIL (exit 1)$' "$TMP/s_ci.txt" && pass "--ci: CI RESULT section" || bad "--ci: no CI RESULT"
  grep -q '^## Flutter review$' "$TMP/summary.md" && grep -q '^| Architecture | 2 | ' "$TMP/summary.md" \
    && grep -q '^| Test gaps | 1 | ' "$TMP/summary.md" && grep -q '^| Error handling | 2 | ' "$TMP/summary.md" \
    && grep -q '^### Top findings$' "$TMP/summary.md" && grep -q '^| high | `ARCH-005` | 1 | ' "$TMP/summary.md" \
    && grep -q '^\*\*Result: FAIL\*\*' "$TMP/summary.md" \
    && pass "\$GITHUB_STEP_SUMMARY: result, section table, top findings" || bad "step summary: $(head -20 "$TMP/summary.md" | tr '\n' ' ')"
  srun --ci --fail-on medium > /dev/null 2>&1; rc=$?
  [ "$rc" = 1 ] && pass "--ci --fail-on medium exits 1" || bad "--ci --fail-on medium exited $rc"
  # baseline: write it with arch_check, then CI passes; a new analyzer error still fails
  python3 -I "$SUITE/flutter-architecture/scripts/arch_check.py" "$TMP/ciapp" --write-baseline "$TMP/bl.json" > /dev/null 2>&1
  srun --ci --fail-on low --baseline "$TMP/bl.json" > "$TMP/s_bl.txt" 2>&1; rc=$?
  [ "$rc" = 0 ] && grep -q '^  architecture: pass (0 new, 2 baselined)$' "$TMP/s_bl.txt" \
    && pass "--ci --baseline: baselined violations pass" || bad "--ci --baseline: rc=$rc $(grep -A3 '^== CI RESULT' "$TMP/s_bl.txt" | tr '\n' ' ')"
  printf 'ERROR|COMPILE_TIME_ERROR|UNDEFINED_METHOD|%s|3|1|1|The method x is not defined.\n' \
    "$TMP/ciapp/lib/main.dart" > "$TMP/analyze_err.txt"
  STUB_ANALYZE="$TMP/analyze_err.txt" srun --ci --baseline "$TMP/bl.json" > "$TMP/s_an.txt" 2>&1; rc=$?
  [ "$rc" = 1 ] && grep -q '^  analyzer: FAIL — 1 error(s) in scope$' "$TMP/s_an.txt" \
    && pass "--ci: an analyzer error exits 1" || bad "--ci analyzer error: rc=$rc"
  STUB_ANALYZE="$TMP/analyze_err.txt" srun --baseline "$TMP/bl.json" > /dev/null 2>&1; rc=$?
  [ "$rc" = 0 ] && pass "no --ci: analyzer errors exit 0" || bad "no --ci with analyzer error exited $rc"
  srun --ci --no-arch > "$TMP/s_noarch.txt" 2>&1; rc=$?
  [ "$rc" = 0 ] && grep -q '^  architecture: skipped (--no-arch)$' "$TMP/s_noarch.txt" \
    && pass "--ci --no-arch: passes, says skipped" || bad "--ci --no-arch: rc=$rc"
  srun --baseline "$TMP/bl.json" > "$TMP/s_blonly.txt" 2>&1
  grep -q '^  summary: 0 new, 2 baselined$' "$TMP/s_blonly.txt" \
    && pass "--baseline without --ci is passed through to arch_check" || bad "--baseline passthrough"
else
  skip "CI architecture exit policy (flutter-architecture not installed)"
fi

# ---- 4b. GitHub Action entry point (scripts/ci_action.sh), flutter=false path: python3 + git only ----
CIA="$SKILL/scripts/ci_action.sh"
bash -n "$CIA" && pass "bash -n ci_action.sh" || bad "bash -n ci_action.sh"
if [ -f "$ARCH_CHECK" ] && command -v git >/dev/null 2>&1; then
  WS="$TMP/ws"; RT="$TMP/rt"; mkdir -p "$WS" "$RT"; cp -R "$FIX" "$WS/app"
  (cd "$WS" && git init -q && git add -A && git -c user.email=t@t -c user.name=t commit -qm init && git branch -q base)
  arun() { : > "$TMP/a_sum.md"; : > "$TMP/a_out.txt"
    (cd "$WS" && env GITHUB_STEP_SUMMARY="$TMP/a_sum.md" GITHUB_OUTPUT="$TMP/a_out.txt" RUNNER_TEMP="$RT" \
       INPUT_PATH=app INPUT_FLUTTER=false "$@" bash "$CIA" > "$TMP/a_log.txt" 2>&1); }
  arun; rc=$?
  [ "$rc" = 1 ] && grep -q '^new-violations=2$' "$TMP/a_out.txt" && grep -q "^report-path=$RT/flutter-pro-skills-report.txt$" "$TMP/a_out.txt" \
    && pass "action (flutter=false): exit 1, outputs new-violations=2 and report-path" || bad "action: rc=$rc $(cat "$TMP/a_out.txt" | tr '\n' ' ')"
  grep -q '^| Architecture | 2 | ' "$TMP/a_sum.md" && grep -q 'Architecture check only' "$TMP/a_sum.md" \
    && pass "action (flutter=false): step summary written" || bad "action: step summary $(head -8 "$TMP/a_sum.md" | tr '\n' ' ')"
  [ -s "$RT/flutter-pro-skills-report.txt" ] && pass "action: report file written" || bad "action: no report file"
  python3 -I "$ARCH_CHECK" "$WS/app" --write-baseline "$WS/arch-baseline.json" > /dev/null 2>&1
  arun INPUT_BASELINE=arch-baseline.json INPUT_FAIL_ON=low; rc=$?
  [ "$rc" = 0 ] && grep -q '^new-violations=0$' "$TMP/a_out.txt" \
    && pass "action: committed baseline -> 0 new, exit 0" || bad "action baseline: rc=$rc $(tail -1 "$TMP/a_log.txt")"
  (cd "$WS" && git checkout -q -b feat && printf "import 'package:dio/dio.dart';\n" >> app/lib/features/cart/presentation/view/checkout_form.dart \
     && git -c user.email=t@t -c user.name=t commit -qam x)
  arun INPUT_BASELINE=arch-baseline.json INPUT_BASE_REF=base; rc=$?
  [ "$rc" = 1 ] && grep -q '^new-violations=1$' "$TMP/a_out.txt" && grep -q '^Scope: diff vs `base` — 1 changed' "$TMP/a_sum.md" \
    && pass "action: base-ref + baseline -> only the PR's new violation fails" || bad "action base-ref: rc=$rc $(cat "$TMP/a_out.txt" | tr '\n' ' ')"
  for kv in INPUT_FAIL_ON=info INPUT_FLUTTER=maybe INPUT_PATH=missing INPUT_BASE_REF=no-such-ref INPUT_BASELINE=nope.json; do
    arun "$kv"; rc=$?
    [ "$rc" = 2 ] && grep -q '^::error::' "$TMP/a_log.txt" && pass "action: bad input $kv exits 2 with ::error::" || bad "action: $kv exited $rc"
  done
else skip "action entry point (needs flutter-architecture + git)"; fi
ACTION_YML="$SKILL/../../action.yml"
if [ -f "$ACTION_YML" ]; then
  ok=1
  for k in '  path:' '  base-ref:' '  fail-on:' '  baseline:' '  flutter:' '  flutter-version:' '  new-violations:' '  report-path:' \
           'using: composite' 'uses: subosito/flutter-action@v2' 'run: flutter pub get' 'skills/dart-flutter-review/scripts/ci_action.sh'; do
    grep -qF -- "$k" "$ACTION_YML" || { ok=0; bad "action.yml lacks: $k"; }
  done
  [ $ok = 1 ] && pass "action.yml declares the contract inputs/outputs and calls ci_action.sh"
else skip "action.yml checks (not in a full suite checkout)"; fi

# ---- 5. integration with the real sibling skills (when installed) -----------
# Passes whether each checker is present or absent: present -> its section prints and doesn't crash;
# absent -> the skipped line. Which ones existed is decided here, at run time.
REAL_TG="$SKILL/../flutter-testing/scripts/test_gaps.py"
REAL_CE="$SKILL/../flutter-error-handling/scripts/check_errors.py"
REAL_SD="$SKILL/../flutter-secure-defaults/scripts/check_secure_defaults.py"
REAL_NV="$SKILL/../flutter-navigation/scripts/check_navigation.py"
REAL_FM="$SKILL/../flutter-forms/scripts/check_forms.py"
REAL_IN="$SKILL/../flutter-i18n/scripts/check_i18n.py"
REAL_SA="$SKILL/../flutter-security-audit/scan.sh"
ARCH_FIX="$SKILL/../flutter-architecture/tests/fixtures"
rm -rf "$TMP/int"; mkdir -p "$TMP/int"; cp -R "$FIX" "$TMP/int/smelly_app"
[ -d "$ARCH_FIX/mvn_violations" ] && cp -R "$ARCH_FIX/mvn_violations" "$TMP/int/mvn_violations"
[ -d "$ARCH_FIX/bloc_clean" ] && cp -R "$ARCH_FIX/bloc_clean" "$TMP/int/bloc_clean"
for app in "$TMP/int"/*; do
  n="$(basename "$app")"
  PATH="$TMP/bin:$PATH" bash "$SKILL/scripts/review.sh" "$app" --no-extra --ci --fail-on low > "$TMP/int_$n.txt" 2>&1; rc=$?
  case "$rc" in 0|1) pass "integration $n: review.sh --ci ran (exit $rc)" ;; *) bad "integration $n: exit $rc" ;; esac
  for pair in "$REAL_TG|== TEST GAPS|flutter-testing" "$REAL_CE|== ERROR HANDLING|flutter-error-handling" \
              "$REAL_SD|== SECURITY DEFAULTS|flutter-secure-defaults" "$REAL_SA|== SECURITY AUDIT|flutter-security-audit" \
              "$REAL_NV|== NAVIGATION|flutter-navigation" "$REAL_FM|== FORMS|flutter-forms" "$REAL_IN|== I18N|flutter-i18n"; do
    f="${pair%%|*}"; rest="${pair#*|}"; h="${rest%%|*}"; sk="${rest#*|}"
    if [ ! -f "$f" ]; then
      grep -q "^$h (skipped: $sk skill not installed)$" "$TMP/int_$n.txt" \
        && pass "integration $n: $h absent -> skipped line" || bad "integration $n: $h absent but no skipped line"
    elif grep -q "^$h (error" "$TMP/int_$n.txt"; then bad "integration $n: $h crashed: $(grep -A3 "^$h" "$TMP/int_$n.txt" | tr '\n' ' ')"
    elif grep -q "^$h" "$TMP/int_$n.txt"; then pass "integration $n: $h section printed (real $sk)"
    else bad "integration $n: no $h section"; fi
  done
done
# diff mode with the real checkers: they take --files without crashing
if command -v git >/dev/null 2>&1; then
  (cd "$TMP/int/smelly_app" && git init -q && git add -A && git -c user.email=t@t -c user.name=t commit -qm init \
     && printf '\n// touched\n' >> lib/features/cart/presentation/view/checkout_form.dart)
  PATH="$TMP/bin:$PATH" bash "$SKILL/scripts/review.sh" "$TMP/int/smelly_app" --no-extra --diff HEAD > "$TMP/int_diff.txt" 2>&1; rc=$?
  [ "$rc" = 0 ] && ! grep -q '^== [A-Z ]* (error' "$TMP/int_diff.txt" \
    && pass "integration diff mode: every installed checker accepts --files" || bad "integration diff: rc=$rc $(grep '(error' "$TMP/int_diff.txt" | tr '\n' ' ')"
fi

[ "$SNAP_BEFORE" = "$(cd "$FIX" && find . -type f | sort | xargs cksum)" ] \
  && pass "read-only: fixture unchanged" || bad "read-only: fixture changed"

echo
[ "$fail" = 0 ] && echo "dart-flutter-review: all tests passed" || echo "dart-flutter-review: SOME TESTS FAILED"
exit "$fail"
