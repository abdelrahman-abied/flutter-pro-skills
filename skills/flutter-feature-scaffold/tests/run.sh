#!/usr/bin/env bash
# Tests for scripts/scaffold.py.
# Needs bash 3.2+ and python3 >= 3.8 (stdlib only). The real compile check runs
# only when `flutter` is on PATH (set SCAFFOLD_SKIP_COMPILE=1 to skip it); every
# pattern whose packages aren't in the offline pub cache is skipped, not failed.
# Prints PASS/FAIL/SKIP lines; exits 1 on any failure.
set -u

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL="$(cd "$HERE/.." && pwd)"
SC="$SKILL/scripts/scaffold.py"
FIX="$HERE/fixtures"
EXP="$HERE/expected"
AC="$SKILL/../flutter-architecture/scripts/arch_check.py"
SECC="$SKILL/../flutter-secure-defaults/scripts/check_secure_defaults.py"
ERRC="$SKILL/../flutter-error-handling/scripts/check_errors.py"
FORMC="$SKILL/../flutter-forms/scripts/check_forms.py"
# v1.1 checkers (CONTRACTS §21): generated code must be clean for these too
V11C="flutter-performance:check_performance flutter-persistence:check_persistence flutter-networking:check_networking flutter-platform-integration:check_platform flutter-design-system:check_design_system flutter-adaptive-layout:check_adaptive flutter-accessibility:check_accessibility"
TMP="$(mktemp -d "${TMPDIR:-/tmp}/scaffold-tests.XXXXXX")"
trap 'rm -rf "$TMP"' EXIT
PASS=0
FAIL=0
SKIP=0
PATTERNS="mvn mvvm bloc cubit getx provider riverpod"

pass() { PASS=$((PASS + 1)); echo "PASS $1"; }
fail() { FAIL=$((FAIL + 1)); echo "FAIL $1"; if [ -n "${2:-}" ]; then printf '     %s\n' "$2" | head -20; fi; }
skip() { SKIP=$((SKIP + 1)); echo "SKIP $1"; }
check() { # label condition-exit-code [detail]
  if [ "$2" -eq 0 ]; then pass "$1"; else fail "$1" "${3:-}"; fi
}

fresh() { rm -rf "$TMP/$2"; cp -R "$FIX/$1" "$TMP/$2"; echo "$TMP/$2"; }
listing() { (cd "$1" && find lib test -type f 2>/dev/null | sort); }
snapshot() { (cd "$1" && find . -type f | sort | while read -r f; do cksum "$f"; done); }
sc() { python3 -I "$SC" "$@"; }
arch_ids() { # dir profile -> "N id@file ..."
  python3 -I "$AC" "$1" --json --profile "$2" | python3 -I -c '
import json, sys
v = json.load(sys.stdin)["violations"]
print(len(v), " ".join("%s@%s:%s" % (x["id"], x["file"], x["line"]) for x in v))'
}
findings() { # checker dir profile min-severity [files] -> "N id@file:line ..." (findings at or above min-severity)
  python3 -I "$1" "$2" --json --profile "$3" ${5:+--files "$5"} | python3 -I -c '
import json, sys
order = {"info": 0, "low": 1, "medium": 2, "high": 3}
f = [x for x in json.load(sys.stdin)["findings"] if order.get(x["severity"], 3) >= order[sys.argv[1]]]
print(len(f), " ".join("%s(%s)@%s:%s" % (x["id"], x["severity"], x["file"], x["line"]) for x in f))' "$4"
}
# The secure-scaffold checklist rules the checkers can't see (flutter-secure-defaults
# references/secure-scaffold-checklist.md), as greps over the generated lib/ files.
# Prints one line per broken rule; empty means every rule holds.
secure_reading() { # project-dir file-list
  local d="$1" libs core
  libs=$(grep '^lib/' "$2" | sed "s|^|$d/|")
  core=$(echo "$libs" | grep '/core/network/')
  grep -nE '\b(print|debugPrint)\(|\bstdout\.' $libs /dev/null | sed 's/^/S-1 no print: /'
  grep -nE "http://|String\.fromEnvironment" $libs /dev/null | sed 's/^/S-2\/S-4 config: /'
  grep -nE '\bDio\(|BaseOptions\(|extends GetConnect' $(echo "$libs" | grep -v '/core/network/') /dev/null |
    sed 's/^/S-5 client built outside core\/network: /'
  for f in $(grep -lE '_client\.(get|post|put|patch|delete)' $libs /dev/null); do
    grep -q 'this\._client' "$f" || echo "S-5 source does not receive its client: $f"
  done
  grep -niE "authorization|bearer |x-api-key" $libs /dev/null | sed 's/^/S-6 auth header: /'
  grep -nE "(\b(print|debugPrint|log)\(|\blogger\.[a-z]+\().*(response|request|body|\.data)" $libs /dev/null |
    sed 's/^/S-8\/S-10 body logged: /'
  grep -nE "\bas (String|int|double|num|bool|Map|List)\b|\]!" $libs /dev/null | sed 's/^/S-14 blind cast: /'
  for f in $(grep -lE 'fromJson\((Object|Map)' $libs /dev/null); do
    grep -q 'throw const FormatException' "$f" || echo "S-14 fromJson without FormatException: $f"
  done
  grep -nE "\.toString\(\)|'\\\$e'|\\\$error\b|\\\$\{e\}" $libs /dev/null |
    grep -v 'String toString() =>' | sed 's/^/S-18\/S-24 raw error text: /'
  [ -n "$core" ] && ! grep -qE 'connectTimeout|timeout:' $core && echo "S-27 shared client without timeouts"
  [ -n "$core" ] && ! grep -q "'https://" $core && echo "S-28 shared client base URL is not https"
  grep -nE 'badCertificateCallback|onBadCertificate|validateCertificate|allowAutoSignedCert *[:=] *true' $libs /dev/null |
    sed 's/^/S-30 certificate override: /'
  grep -nE 'LogInterceptor\(|PrettyDioLogger' $libs /dev/null | sed 's/^/S-29 HTTP logger: /'
  grep -nE 'WebView|launchUrl|SharedPreferences|GetStorage|HydratedBloc' $libs /dev/null | sed 's/^/S-13\/S-20\/S-26 not in templates: /'
}

# --------------------------------------------------------------------------
echo "-- usage errors"
d=$(fresh ff_app usage)
before=$(snapshot "$d")
for bad in Cart my-feature class 1abc cart__x state ''; do
  sc "$d" "$bad" --profile mvn >/dev/null 2>&1
  rc=$?
  [ $rc -eq 2 ]; check "rejects feature name '$bad' (exit 2)" $? "exit $rc"
done
out=$(sc "$d" My-Feature --profile mvn 2>&1)
echo "$out" | grep -q "'my_feature'"; check "suggests a snake_case name" $? "$out"
sc "$TMP/does-not-exist" cart >/dev/null 2>&1
[ $? -eq 2 ]; check "no pubspec.yaml -> exit 2" $?
out=$(sc "$d" cart 2>&1)
rc=$?
[ $rc -eq 2 ] && echo "$out" | grep -q 'could not infer a supported pattern'
check "auto on a project with no state management -> exit 2 and asks for --profile" $? "exit $rc: $out"
sc "$d" cart --profile mvn --entity movie >/dev/null 2>&1
[ $? -eq 2 ]; check "rejects a non-UpperCamel --entity" $?
[ "$before" = "$(snapshot "$d")" ]; check "usage errors write nothing" $?

# --------------------------------------------------------------------------
echo "-- dry run writes nothing"
for fx in ff_app lf_app; do
  d=$(fresh $fx dry-$fx)
  before=$(snapshot "$d")
  ok=0
  for p in $PATTERNS; do
    for c in "" "--clean"; do
      out=$(sc "$d" orders --profile $p $c 2>&1) || { ok=1; echo "     $p $c: $out" | head -3; }
      name=$fx-$p${c:+-clean}
      [ $p = mvn ] && name=$fx-mvn
      want=$(wc -l < "$EXP/$name.txt" | tr -d ' ')
      got=$(echo "$out" | grep -c '^  + ')
      [ "$want" = "$got" ] || { ok=1; echo "     $name: dry run lists $got files, expected $want"; }
    done
  done
  [ $ok -eq 0 ]; check "$fx: dry run of every profile lists the expected files and exits 0" $?
  [ "$before" = "$(snapshot "$d")" ]; check "$fx: dry run of every profile leaves the project untouched" $?
done

# --------------------------------------------------------------------------
echo "-- write: file lists, arch_check, idempotence"
for fx in ff_app lf_app; do
  for p in $PATTERNS; do
    for c in "" "--clean"; do
      [ $p = mvn ] && [ -n "$c" ] && continue
      name=$fx-$p${c:+-clean}
      d=$(fresh $fx "w-$name")
      pub_before=$(cksum < "$d/pubspec.yaml")
      base=$(listing "$d")
      out=$(sc "$d" orders --profile $p $c --write 2>&1)
      rc=$?
      [ $rc -eq 0 ]; check "$name: --write exits 0" $? "$out"
      got=$(listing "$d" | comm -13 <(echo "$base") -)
      [ "$got" = "$(cat "$EXP/$name.txt")" ]
      check "$name: generated file list matches expected/$name.txt" $? "$(diff <(echo "$got") "$EXP/$name.txt")"
      n_created=$(echo "$out" | grep -c '^  created ')
      [ "$n_created" = "$(wc -l < "$EXP/$name.txt" | tr -d ' ')" ]; check "$name: reports every created file" $?
      [ "$pub_before" = "$(cksum < "$d/pubspec.yaml")" ]; check "$name: pubspec.yaml untouched" $?
      ap=$p; [ $p = cubit ] && ap=bloc
      if [ -f "$AC" ]; then
        v=$(arch_ids "$d" $ap)
        [ "${v%% *}" = "0" ]; check "$name: arch_check --profile $ap reports zero violations" $? "$v"
      else
        skip "$name: arch_check (flutter-architecture skill not installed)"
      fi
      # secure by default: the sibling checkers find nothing in the generated feature
      echo "$got" > "$TMP/$name.files"
      if [ -f "$SECC" ]; then
        v=$(findings "$SECC" "$d" $ap info)
        [ "${v%% *}" = "0" ]; check "$name: check_secure_defaults reports zero findings" $? "$v"
      else
        skip "$name: check_secure_defaults (flutter-secure-defaults skill not installed)"
      fi
      if [ -f "$ERRC" ]; then
        v=$(findings "$ERRC" "$d" $ap medium)
        [ "${v%% *}" = "0" ]; check "$name: check_errors reports zero high/medium findings" $? "$v"
        v=$(findings "$ERRC" "$d" $ap info "$TMP/$name.files")
        [ "${v%% *}" = "0" ]; check "$name: check_errors reports nothing at all in the generated files" $? "$v"
      else
        skip "$name: check_errors (flutter-error-handling skill not installed)"
      fi
      if [ -f "$FORMC" ]; then
        v=$(findings "$FORMC" "$d" $ap info)
        [ "${v%% *}" = "0" ]; check "$name: check_forms reports zero findings" $? "$v"
      else
        skip "$name: check_forms (flutter-forms skill not installed)"
      fi
      for kv in $V11C; do
        ck="$SKILL/../${kv%%:*}/scripts/${kv#*:}.py"
        if [ -f "$ck" ]; then
          v=$(findings "$ck" "$d" $ap info "$TMP/$name.files")
          [ "${v%% *}" = "0" ]; check "$name: ${kv#*:} reports zero findings in the generated files" $? "$v"
        else
          skip "$name: ${kv#*:} (${kv%%:*} skill not installed)"
        fi
      done
      v=$(secure_reading "$d" "$TMP/$name.files")
      [ -z "$v" ]; check "$name: secure-scaffold checklist greps (S-1..S-30) all hold" $? "$v"
      snap=$(snapshot "$d")
      sc "$d" orders --profile $p $c --write >/dev/null 2>&1
      [ $? -eq 2 ]; check "$name: second --write refuses an existing feature (exit 2)" $?
      out=$(sc "$d" orders --profile $p $c --write --force-dir 2>&1)
      [ "$(echo "$out" | grep -c '^  created ')" = "0" ] && echo "$out" | grep -q '^  skipped .*(exists, not overwritten)'
      check "$name: --force-dir re-run creates nothing and reports skips" $? "$out"
      [ "$snap" = "$(snapshot "$d")" ]; check "$name: re-runs change no file" $?
    done
  done
done

# --------------------------------------------------------------------------
echo "-- never overwrites"
d=$(fresh ff_app overwrite)
victim=lib/features/orders/presentation/view/orders_view.dart
mkdir -p "$d/$(dirname $victim)"
echo '// hand-written, keep me' > "$d/$victim"
base=$(listing "$d")
sc "$d" orders --profile mvn --write >/dev/null 2>&1
rc=$?
[ $rc -eq 2 ] && [ "$base" = "$(listing "$d")" ]
check "existing feature folder without --force-dir: exit 2, nothing written" $? "exit $rc"
out=$(sc "$d" orders --profile mvn --write --force-dir 2>&1)
[ "$(cat "$d/$victim")" = '// hand-written, keep me' ]; check "pre-existing file left byte-for-byte untouched" $?
echo "$out" | grep -q "^  skipped $victim (exists, not overwritten)"; check "pre-existing file reported as skipped" $? "$out"
[ "$(echo "$out" | grep -c '^  created ')" = "$(($(wc -l < "$EXP/ff_app-mvn.txt") - 1))" ]
check "all other files still created" $?
out=$(sc "$d" orders --profile mvn --force-dir 2>&1)
echo "$out" | grep -q "^  = $victim  \[exists: will be skipped\]"; check "dry run marks the existing file '='" $?

# --------------------------------------------------------------------------
echo "-- convention inference"
d=$(fresh mvn_conventions conv)
out=$(sc "$d" cart --write 2>&1)
check "mvn_conventions: auto --write exits 0" $? "$out"
echo "$out" | grep -q '^  pattern: mvn (detected'; check "detects mvn" $?
F=lib/features/cart/presentation
[ -f "$d/$F/notifiers/cart_notifier.dart" ] && [ ! -e "$d/$F/notifier" ]; check "copies plural notifiers/" $?
[ -f "$d/$F/pages/cart_page.dart" ] && grep -q 'class CartPage extends ConsumerWidget' "$d/$F/pages/cart_page.dart"
check "copies pages/ + Page suffix (CartPage)" $?
[ -f "$d/test/features/cart/presentation/pages/cart_page_test.dart" ]; check "test mirrors the inferred path" $?
[ -f "$d/$F/widgets/cart_widget.dart" ]; check "copies plural widgets/" $?
grep -q "^import 'package:mvn_conventions/features/cart/domain/usecases/cart_usecase.dart';" "$d/$F/notifiers/cart_notifier.dart"
check "copies package-style imports" $?
! grep -q "^import '\.\./" "$d/$F/notifiers/cart_notifier.dart"; check "no relative imports when the project uses package imports" $?
grep -q 'ref.watch(cartProvider)' "$d/$F/pages/cart_page.dart" && grep -q 'ref.mounted' "$d/$F/notifiers/cart_notifier.dart"
check "riverpod_generator 4.x: provider named cartProvider, ref.mounted guard" $?
if [ -f "$AC" ]; then
  v=$(arch_ids "$d" mvn); [ "${v%% *}" = "0" ]; check "mvn_conventions: arch_check zero violations after scaffolding" $? "$v"
fi
d=$(fresh mvn_conventions conv-legacy)
sed 's/riverpod_generator: \^4.0.0/riverpod_generator: ^2.6.0/' "$FIX/mvn_conventions/pubspec.yaml" > "$d/pubspec.yaml"
sc "$d" cart --write >/dev/null 2>&1
grep -q 'ref.watch(cartNotifierProvider)' "$d/$F/pages/cart_page.dart" && ! grep -q 'ref.mounted' "$d/$F/notifiers/cart_notifier.dart"
check "riverpod_generator 2.x: provider named cartNotifierProvider, no ref.mounted" $?
d=$(fresh ff_app conv-relative)
sc "$d" orders --profile mvn --write >/dev/null 2>&1
grep -q "^import '\.\./\.\./domain/usecases/orders_usecase.dart';" "$d/lib/features/orders/presentation/notifier/orders_notifier.dart"
check "relative imports when the project uses them" $?
grep -q "^import 'package:ff_app/features/orders/" "$d/test/features/orders/presentation/notifier/orders_notifier_test.dart"
check "tests always use package imports" $?
d=$(fresh lf_app conv-mvvm)
out=$(sc "$d" orders --profile mvvm --write 2>&1)
echo "$out" | grep -q 'reusing existing Result: lib/core/result.dart' && [ ! -e "$d/lib/utils/result.dart" ] &&
  grep -q "^import '\.\./core/result.dart';" "$d/lib/utils/command.dart"
check "mvvm reuses the project's Compass-shaped Result" $? "$out"
d=$(fresh ff_app conv-entity)
sc "$d" orders --profile mvn --entity Movie --write >/dev/null 2>&1
grep -q '^class MovieEntity {' "$d/lib/features/orders/domain/entities/movie_entity.dart" 2>/dev/null
check "--entity Movie -> movie_entity.dart / MovieEntity" $?
d=$(fresh ff_app conv-sdk)
sc "$d" orders --profile provider --write >/dev/null 2>&1
grep -q 'required OrdersRepository ordersRepository}) : _ordersRepository = ordersRepository;' \
  "$d/lib/features/orders/presentation/notifiers/orders_notifier.dart"
check "SDK < 3.12: classic initializer-list constructor" $?
d=$(fresh ff_app conv-sdk312)
sed 's/sdk: \^3.5.0/sdk: ^3.12.0/' "$FIX/ff_app/pubspec.yaml" > "$d/pubspec.yaml"
sc "$d" orders --profile provider --write >/dev/null 2>&1
grep -q 'OrdersNotifier({required this._ordersRepository});' "$d/lib/features/orders/presentation/notifiers/orders_notifier.dart"
check "SDK >= 3.12: private named parameter constructor" $?

# --------------------------------------------------------------------------
echo "-- secure by default: shared client and failures"
for p in mvn bloc getx; do
  d=$(fresh ff_app shared-$p)
  sc "$d" orders --profile $p --write >/dev/null 2>&1
  core=$(cd "$d" && find lib -path '*/core/*' -type f | sort)
  before=$(cd "$d" && for f in $core; do cksum "$f"; done)
  out=$(sc "$d" invoices --profile $p --write 2>&1)
  n=$(echo "$out" | grep -c '^  reused .*/core/.*\[shared: exists, reused as is\]')
  [ "$n" = "2" ] && [ "$before" = "$(cd "$d" && for f in $core; do cksum "$f"; done)" ] &&
    ! echo "$out" | grep -q '^  created .*/core/'
  check "$p: a second feature reuses the shared failure type and HTTP client untouched" $? "$out"
  if [ -f "$SECC" ] && [ -f "$ERRC" ]; then
    ap=$p; v=$(findings "$SECC" "$d" $ap info); w=$(findings "$ERRC" "$d" $ap medium)
    [ "${v%% *}" = "0" ] && [ "${w%% *}" = "0" ]; check "$p: two features side by side stay clean (security, errors)" $? "$v / $w"
  fi
done
d=$(fresh ff_app shared-note)
mkdir -p "$d/lib/core/api"
printf "import 'package:dio/dio.dart';\n\nfinal dio = Dio(BaseOptions(baseUrl: 'https://api.shop.dev'));\n" > "$d/lib/core/api/dio.dart"
sc "$d" orders --profile bloc 2>&1 | grep -q '^  note: the project already configures an HTTP client in lib/core/api/dio.dart'
check "points at the project's existing HTTP client instead of silently adding a second one (S-31)" $?
# the checklist greps must actually catch a violation (guards against a grep that never matches)
d=$(fresh ff_app planted)
sc "$d" orders --profile riverpod --write >/dev/null 2>&1
src=lib/features/orders/data/sources/orders_source.dart
cat >> "$d/$src" <<'DART'
String leak(Response<Object?> r, Object e) {
  print(r.data);
  return (r.data as Map)['token'] as String;
}
String show(Object e) => e.toString();
DART
echo "$src" > "$TMP/planted.files"
v=$(secure_reading "$d" "$TMP/planted.files")
echo "$v" | grep -q '^S-1 ' && echo "$v" | grep -q '^S-14 ' && echo "$v" | grep -q '^S-18'
check "checklist greps catch a planted print, blind cast and raw error text" $? "$v"

# --------------------------------------------------------------------------
echo "-- dependencies"
deps() { sc "$TMP/$1" orders --profile $2 2>&1 | grep -E '^  (run|missing):'; }
d=$(fresh ff_app deps-ff)
deps deps-ff mvn | grep -qx '  run: flutter pub add dio flutter_riverpod meta riverpod_annotation'
check "mvn: prints dio, flutter_riverpod, meta, riverpod_annotation" $?
deps deps-ff mvn | grep -qx '  run: flutter pub add dev:build_runner dev:riverpod_generator'
check "mvn: prints dev:build_runner, dev:riverpod_generator" $?
deps deps-ff bloc | grep -qx '  run: flutter pub add dio equatable flutter_bloc' &&
  deps deps-ff bloc | grep -qx '  run: flutter pub add dev:bloc_test'
check "bloc: prints dio, flutter_bloc, equatable and dev:bloc_test" $?
deps deps-ff getx | grep -qx '  run: flutter pub add get'; check "getx: prints get only (GetConnect is the client)" $?
deps deps-ff provider | grep -qx '  run: flutter pub add dio provider'; check "provider: prints dio, provider" $?
d=$(fresh lf_app deps-lf)
deps deps-lf provider | grep -qx '  missing: none'; check "nothing missing when pubspec already has it" $?
sc "$d" orders --profile riverpod 2>&1 | grep -q 'dart run build_runner build -d'; check "riverpod: prints the codegen command" $?

# --------------------------------------------------------------------------
echo "-- fallback without the flutter-architecture skill"
mkdir -p "$TMP/solo"
cp -R "$SKILL" "$TMP/solo/flutter-feature-scaffold"
d=$(fresh ff_app solo-app)
base=$(listing "$d")
out=$(python3 -I "$TMP/solo/flutter-feature-scaffold/scripts/scaffold.py" "$d" orders --profile bloc --write 2>&1)
echo "$out" | grep -q 'built-in scan (flutter-architecture skill not installed'; check "says it fell back to the built-in scan" $? "$out"
[ "$(listing "$d" | comm -13 <(echo "$base") -)" = "$(cat "$EXP/ff_app-bloc.txt")" ]
check "fallback produces the same bloc file list" $?

# --------------------------------------------------------------------------
echo "-- real compile check (flutter create + pub add --offline + dart analyze + flutter test)"
compile_family() { # name sdk-constraint "<variant args>"...
  local fam="$1" sdk="$2" P W v out tokens codegen=0 t0=$SECONDS missing_dev="" partial="" t libtok devtok
  shift 2
  P="$C/$fam"
  W="$C/$fam-work"
  rm -rf "$P"
  cp -R "$C/base" "$P"
  if [ -n "$sdk" ]; then
    sed "s/^  sdk: .*/  sdk: $sdk/" "$P/pubspec.yaml" > "$P/pubspec.tmp" && mv "$P/pubspec.tmp" "$P/pubspec.yaml"
  fi
  tokens=""
  for v in "$@"; do
    out=$(python3 -I "$SC" "$P" $v 2>&1) || { fail "compile $fam: dry run '$v'" "$out"; return; }
    tokens="$tokens $(echo "$out" | sed -n 's/^  run: flutter pub add //p' | tr '\n' ' ')"
    echo "$out" | grep -q 'build_runner build' && codegen=1
  done
  tokens=$(echo $tokens | tr ' ' '\n' | sort -u | tr '\n' ' ')
  if [ -n "${tokens// /}" ]; then
    if ! (cd "$P" && flutter pub add --offline $tokens > "$P/pub.log" 2>&1); then
      libtok=$(echo $tokens | tr ' ' '\n' | grep -v '^dev:' | tr '\n' ' ')
      devtok=$(echo $tokens | tr ' ' '\n' | grep '^dev:' | tr '\n' ' ')
      if [ -n "${devtok// /}" ] && (cd "$P" && flutter pub add --offline $libtok > "$P/pub.log" 2>&1); then
        # Only test packages are missing (bloc_test): still compile lib/ and the tests that don't need them.
        for t in $devtok; do
          (cd "$P" && flutter pub add --offline "$t" >> "$P/pub.log" 2>&1) || missing_dev="$missing_dev ${t#dev:}"
        done
      else
        skip "compile $fam: not in the offline pub cache ($tokens): $(grep -m1 -iE 'could not|because|failed' "$P/pub.log")"
        return
      fi
    fi
  fi
  for v in "$@"; do
    rm -rf "$W"
    mkdir -p "$W/lib"
    cp "$P/pubspec.yaml" "$P/pubspec.lock" "$W/"
    cp "$P/lib/main.dart" "$W/lib/"
    out=$(python3 -I "$SC" "$W" $v --write 2>&1) || { fail "compile $fam: --write '$v'" "$out"; return; }
    cp -R "$W/lib" "$W/test" "$P/"
  done
  if [ -n "$missing_dev" ]; then
    local dropped=0 f pkg
    for pkg in $missing_dev; do
      for f in $(grep -rl "package:$pkg/" "$P/test"); do rm "$f"; dropped=$((dropped + 1)); done
    done
    partial=" (partial: without$missing_dev)"
    skip "compile $fam: $dropped test file(s) need$missing_dev, which is not in the offline pub cache"
  fi
  if [ $codegen -eq 1 ]; then
    if ! (cd "$P" && dart run build_runner build -d > "$P/codegen.log" 2>&1); then
      fail "compile $fam: build_runner" "$(tail -15 "$P/codegen.log")"
      return
    fi
  fi
  (cd "$P" && dart analyze lib test > "$P/analyze.log" 2>&1)
  local rc=$?
  local bad infos
  bad=$(grep -E '^ *(error|warning) - ' "$P/analyze.log")
  infos=$(grep -cE '^ *info - ' "$P/analyze.log")
  if [ $rc -eq 0 ] && [ -z "$bad" ]; then
    pass "compile $fam: dart analyze, 0 errors/warnings ($infos infos)$partial [$*]"
  else
    fail "compile $fam: dart analyze (exit $rc)" "$(grep -E ' - ' "$P/analyze.log" | head -15)"
  fi
  if (cd "$P" && flutter test test > "$P/test.log" 2>&1); then
    pass "compile $fam: generated tests pass ($(grep -oE '\+[0-9]+' "$P/test.log" | tail -1 | tr -d +) tests, $((SECONDS - t0))s)$partial"
  else
    fail "compile $fam: flutter test" "$(grep -E 'FAILED|Error|Expected|Actual' "$P/test.log" | head -15)"
  fi
}

if [ -n "${SCAFFOLD_SKIP_COMPILE:-}" ]; then
  skip "compile check (SCAFFOLD_SKIP_COMPILE is set)"
elif ! command -v flutter >/dev/null 2>&1; then
  skip "compile check (flutter not on PATH)"
else
  C="$TMP/compile"
  mkdir -p "$C"
  if ! (cd "$C" && flutter create --offline --empty --project-name scaffold_check base > "$C/create.log" 2>&1); then
    skip "compile check (flutter create --offline failed: $(tail -1 "$C/create.log"))"
  else
    compile_family riverpod "" "catalog --profile mvn" "orders --profile riverpod" "invoices --profile riverpod --clean"
    compile_family provider "" "bookings --profile mvvm" "trips --profile mvvm --clean" \
      "carts --profile provider" "wishes --profile provider --clean"
    compile_family provider-sdk38 "^3.8.0" "bookings --profile mvvm" "trips --profile mvvm --clean" \
      "carts --profile provider" "wishes --profile provider --clean"
    compile_family bloc "" "todos --profile bloc" "stats --profile cubit" "notes --profile bloc --clean" \
      "tasks --profile cubit --clean"
    compile_family getx "" "home --profile getx" "account --profile getx --clean"
  fi
fi

echo
echo "flutter-feature-scaffold: $PASS passed, $FAIL failed, $SKIP skipped"
[ $FAIL -eq 0 ]
