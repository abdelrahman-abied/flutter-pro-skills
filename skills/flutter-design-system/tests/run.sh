#!/usr/bin/env bash
# Tests for flutter-design-system/scripts/check_design_system.py.
# No Flutter SDK or pub get needed: the checker is static. bash 3.2 compatible.
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL="$(cd "$HERE/.." && pwd)"
CHECK="$SKILL/scripts/check_design_system.py"
FIX="$HERE/fixtures"
TMP="$(mktemp -d "${TMPDIR:-/tmp}/dscheck.XXXXXX")"
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
def files(rid):
    return sorted(f['file'] for f in of(rid))
ok = eval(sys.argv[2])
if not ok:
    sys.stderr.write('    expression was false: %s\n' % sys.argv[2])
    sys.stderr.write('    findings: %s\n' % sorted((f['id'], f['severity'], f['file'], f['line']) for f in d['findings']))
sys.exit(0 if ok else 1)
PY
  then pass "$name"; else bad "$name"; fi
}

checksum() { (cd "$1" && find . -type f | LC_ALL=C sort | while read -r f; do cksum "$f"; done); }
run() { python3 -I "$CHECK" "$@"; }

# --- syntax: stays Python 3.8 compatible
if python3 -I -c "import ast,sys; ast.parse(open(sys.argv[1]).read(), feature_version=(3, 8))" "$CHECK" 2>/dev/null; then
  pass "check_design_system.py parses as Python 3.8"
else
  bad "check_design_system.py parses as Python 3.8"
fi

# --- violations fixture: every rule fires
before="$(checksum "$FIX/violations")"
run "$FIX/violations" --json > "$TMP/v.json"; rc=$?
[ $rc = 0 ] && pass "violations: exit 0 with findings" || bad "violations: exit 0 with findings (got $rc)"
after="$(checksum "$FIX/violations")"
[ "$before" = "$after" ] && pass "read-only: fixture unchanged" || bad "read-only: fixture unchanged"
for n in 001 002 003 004 005 006 007 008 009 010 011 012; do
  assert "violations: DS-$n triggered" "$TMP/v.json" "'DS-$n' in ids"
done
V=lib/features/orders/presentation/view/orders_view.dart
T=lib/core/design_system/theme
assert "DS-001 low, one finding per file with a count"     "$TMP/v.json" "sev('DS-001') == ['low'] and '(+2 more in this file)' in of('DS-001')[0]['evidence']"
assert "DS-002 low on TextStyle(fontSize: 22)"             "$TMP/v.json" "at('$V', 17, 'DS-002')[0]['severity'] == 'low'"
assert "DS-003 fires because the project has AppSpacing"   "$TMP/v.json" "'AppSpacing' in of('DS-003')[0]['note'] and 'AppSpacing' in d['stats']['spacing_scale']"
assert "DS-004 fires because the project has AppRadius"    "$TMP/v.json" "at('$V', 22, 'DS-004') and 'AppRadius' in d['stats']['radius_scale']"
assert "DS-005 high: light-only extension read with !"     "$TMP/v.json" "at('$T/app_theme.dart', 14, 'DS-005')[0]['severity'] == 'high' and 'AppColors' in at('$T/app_theme.dart', 14, 'DS-005')[0]['evidence']"
assert "DS-005 high: extension in no theme, read with !"   "$TMP/v.json" "at('$V', 11, 'DS-005')[0]['severity'] == 'high'"
assert "DS-005 skips extensions registered in both themes" "$TMP/v.json" "not [f for f in of('DS-005') if 'StatusColors' in f['evidence']]"
assert "DS-006 low on a lerp that returns this"            "$TMP/v.json" "at('$T/status_colors.dart', 17, 'DS-006')[0]['severity'] == 'low'"
assert "DS-006 skips lerps that interpolate"               "$TMP/v.json" "files('DS-006') == ['$T/status_colors.dart']"
assert "DS-007 medium on a non-final extension field"      "$TMP/v.json" "at('$T/status_colors.dart', 6, 'DS-007')[0]['severity'] == 'medium'"
assert "DS-008 medium, MVN note"                           "$TMP/v.json" "of('DS-008')[0]['severity'] == 'medium' and 'MVN:' in of('DS-008')[0]['note']"
assert "DS-009 low on Theme.of(context).brightness =="     "$TMP/v.json" "at('$V', 10, 'DS-009')[0]['severity'] == 'low'"
assert "DS-010 medium on Theme(data: ThemeData(...))"      "$TMP/v.json" "of('DS-010')[0]['severity'] == 'medium' and of('DS-010')[0]['file'].endswith('promo_banner.dart')"
assert "DS-011 medium under mvn, with the MVN fix"         "$TMP/v.json" "of('DS-011')[0]['severity'] == 'medium' and of('DS-011')[0]['note'].startswith('MVN:') and '(+1 more' in of('DS-011')[0]['evidence']"
assert "DS-011 ignores the notifier without visual fields" "$TMP/v.json" "files('DS-011') == ['lib/features/orders/presentation/state/order_state.dart']"
assert "DS-012 low, reported once"                         "$TMP/v.json" "sev('DS-012') == ['low']"
assert "uses arch_check files[] when installed"            "$TMP/v.json" "d['classification'] == 'arch_check files[]' or d['classification'].startswith('path-based fallback (flutter-architecture')"

# --- JSON contract (CONTRACTS §22)
assert "JSON: schema and top-level keys" "$TMP/v.json" "d['schema'] == 'flutter-pro-skills/design-system@1' and set(d) >= {'schema','root','package','profile','classification','stats','findings','suppressed'}"
assert "JSON: finding keys"              "$TMP/v.json" "all(set(f) == {'id','name','severity','file','line','evidence','message','note'} for f in d['findings'])"
assert "JSON: profile and stats keys"    "$TMP/v.json" "set(d['profile']) >= {'presentation','source'} and set(d['stats']) >= {'files','themes','theme_extensions','spacing_scale','radius_scale','design_system','literal_colors'}"
assert "JSON: severities are known"      "$TMP/v.json" "all(f['severity'] in ('high','medium','low','info') for f in d['findings'])"
assert "JSON: package from pubspec"      "$TMP/v.json" "d['package'] == 'ds_violations'"

# --- text output
run "$FIX/violations" --max 1 > "$TMP/v.txt"
head -1 "$TMP/v.txt" | grep -q '^== DESIGN SYSTEM$' && pass "text: header" || bad "text: header"
grep -q '^  profile: mvn' "$TMP/v.txt" && grep -q '^  classification: ' "$TMP/v.txt" && grep -q '^  scanned: ' "$TMP/v.txt" && pass "text: profile/classification/scanned lines" || bad "text: profile/classification/scanned lines"
grep -Eq '^  \[DS-005\] theme-extension-not-registered \(high\) x2 — ' "$TMP/v.txt" && pass "text: group line format" || bad "text: group line format"
grep -Eq '^      lib/[^ ]+\.dart:[0-9]+  ' "$TMP/v.txt" && pass "text: location lines" || bad "text: location lines"
grep -Eq '^      \.\.\. 1 more$' "$TMP/v.txt" && pass "text: --max collapses extra locations" || bad "text: --max collapses extra locations"

# --- --files (file list and comma list)
echo "lib/features/orders/presentation/widget/promo_banner.dart" > "$TMP/files.txt"
run "$FIX/violations" --json --files "$TMP/files.txt" > "$TMP/f.json"
assert "--files: only listed files reported" "$TMP/f.json" "ids == {'DS-010'}"
run "$FIX/violations" --json --files "$V,$T/status_colors.dart" > "$TMP/f2.json"
assert "--files: comma list, project-wide facts still used" "$TMP/f2.json" "ids == {'DS-001','DS-002','DS-003','DS-004','DS-005','DS-006','DS-007','DS-009'} and all(f['file'] in ('$V', '$T/status_colors.dart') for f in d['findings'])"

# --- clean fixture: design-system code and near-misses
before="$(checksum "$FIX/clean")"
run "$FIX/clean" --json > "$TMP/c.json"
assert "clean: zero findings" "$TMP/c.json" "d['findings'] == [] and d['suppressed'] == []"
assert "clean: tokens, themes and the extension were seen" "$TMP/c.json" "d['stats']['theme_extensions'] == 1 and d['stats']['spacing_scale'] and d['stats']['design_system']"
run "$FIX/clean" > "$TMP/c.txt"
grep -q '^  no design system findings$' "$TMP/c.txt" && pass "clean: text says no findings" || bad "clean: text says no findings"
[ "$before" = "$(checksum "$FIX/clean")" ] && pass "read-only: clean fixture unchanged" || bad "read-only: clean fixture unchanged"

# --- app-aware grading: no theme at all means info
run "$FIX/notheme" --json > "$TMP/n0.json"
assert "no theme: DS-001/002 graded info" "$TMP/n0.json" "ids == {'DS-001','DS-002'} and all(f['severity'] == 'info' for f in d['findings'])"

# --- suppression
run "$FIX/suppressed" --json > "$TMP/s.json"
assert "suppress: unsuppressed hit still reported" "$TMP/s.json" "[(f['id'], f['file'], f['line']) for f in d['findings']] == [('DS-002', 'lib/widgets/line_ignored.dart', 13)]"
assert "suppress: line-above, same-line and file comments honoured" "$TMP/s.json" "sorted((s['id'], s['file'], s['line']) for s in d['suppressed']) == [('DS-001','lib/widgets/line_ignored.dart',11), ('DS-001','lib/widgets/line_ignored.dart',12), ('DS-002','lib/widgets/file_ignored.dart',8)]"
assert "suppress: reasons kept" "$TMP/s.json" "all(s['reason'] and s['reason'] != '(no reason given)' for s in d['suppressed'])"
run "$FIX/suppressed" | grep -q '^  suppressed: 3 (see --json)$' && pass "suppress: text summary line" || bad "suppress: text summary line"

# --- fallback without the flutter-architecture sibling
mkdir -p "$TMP/lonely/scripts"
cp "$CHECK" "$TMP/lonely/scripts/check_design_system.py"
python3 -I "$TMP/lonely/scripts/check_design_system.py" "$FIX/violations" --json > "$TMP/fb.json"
assert "fallback: says it used path-based classification" "$TMP/fb.json" "d['classification'].startswith('path-based fallback')"
assert "fallback: every rule still fires" "$TMP/fb.json" "ids == {'DS-%03d' % i for i in range(1, 13)}"
assert "fallback: profile detected from pubspec/folders" "$TMP/fb.json" "d['profile']['presentation'] == 'mvn' and d['profile']['source'].startswith('fallback')"
python3 -I "$TMP/lonely/scripts/check_design_system.py" "$FIX/violations" | grep -q '^  classification: path-based fallback' && pass "fallback: text output says so" || bad "fallback: text output says so"
python3 -I "$TMP/lonely/scripts/check_design_system.py" "$FIX/clean" --json > "$TMP/fbc.json"
assert "fallback: clean fixture still zero" "$TMP/fbc.json" "d['findings'] == []"

# --- --profile override changes the notes and DS-011's grade
run "$FIX/violations" --json --profile bloc > "$TMP/p.json"
assert "--profile bloc: Bloc notes" "$TMP/p.json" "d['profile']['presentation'] == 'bloc' and d['profile']['source'].startswith('declared') and of('DS-011')[0]['note'].startswith('Bloc:') and 'Bloc:' in of('DS-008')[0]['note']"
run "$FIX/violations" --json --profile getx > "$TMP/pg.json"
assert "--profile getx: DS-011 drops to low" "$TMP/pg.json" "sev('DS-011') == ['low'] and of('DS-011')[0]['note'].startswith('GetX:')"

# --- usage errors and edge cases
run "$TMP" >/dev/null 2>&1; rc=$?
[ $rc = 2 ] && pass "exit 2 without pubspec.yaml" || bad "exit 2 without pubspec.yaml (got $rc)"
run "$FIX/clean" --bogus >/dev/null 2>&1; rc=$?
[ $rc = 2 ] && pass "exit 2 on unknown option" || bad "exit 2 on unknown option (got $rc)"
run "$FIX/clean" --profile nope >/dev/null 2>&1; rc=$?
[ $rc = 2 ] && pass "exit 2 on unknown profile" || bad "exit 2 on unknown profile (got $rc)"
python3 -I "$CHECK" >/dev/null 2>&1; rc=$?
[ $rc = 2 ] && pass "exit 2 without arguments" || bad "exit 2 without arguments (got $rc)"
mkdir -p "$TMP/nolib"; printf 'name: nolib\n' > "$TMP/nolib/pubspec.yaml"
run "$TMP/nolib" --json > "$TMP/n.json"; rc=$?
[ $rc = 0 ] && pass "no lib/: exit 0" || bad "no lib/: exit 0 (got $rc)"
assert "no lib/: empty report" "$TMP/n.json" "d['findings'] == [] and d['stats']['files'] == 0"

# --- calibration regressions (references/rules.md, Calibration): FP gone, related TP still fires
run "$FIX/calib_compass_dimens" --json > "$TMP/k1.json"
assert "calib compass: screen-size Dimens is not a spacing scale (no DS-003)" "$TMP/k1.json" "'DS-003' not in ids and d['stats']['spacing_scale'] == ''"
assert "calib compass: TP DS-003 still fires with a real scale (violations)" "$TMP/v.json" "of('DS-003')"
run "$FIX/calib_compass_ext_fallback" --json > "$TMP/k2.json"
assert "calib compass: fallback after extension<T>()? is not DS-001" "$TMP/k2.json" "files('DS-001') == ['lib/ui/home/widgets/home_title.dart']"
run "$FIX/calib_compass_scrim" --json > "$TMP/k3.json"
assert "calib compass: shadows and image tints are not DS-001" "$TMP/k3.json" "not [f for f in of('DS-001') if 'result_card' in f['file']]"
assert "calib compass: lone Colors.white is info, grey[200] stays low" "$TMP/k3.json" "[(f['file'].split('/')[-1], f['severity']) for f in of('DS-001')] == [('activity_entry.dart', 'low'), ('error_indicator.dart', 'info')]"
run "$FIX/calib_bloc_weather" --json > "$TMP/k4.json"
assert "calib bloc weather: enum->Color mapping, colour maths and emoji size are clean" "$TMP/k4.json" "'DS-001' not in ids and files('DS-002') == ['lib/weather/widgets/weather_populated.dart'] and of('DS-002')[0]['line'] == 13"
run "$FIX/calib_bloc_shopping_model" --json > "$TMP/k5.json"
assert "calib bloc shopping: a colour in a plain model is not DS-001; the page still is" "$TMP/k5.json" "files('DS-001') == ['lib/catalog/view/catalog_page.dart']"
run "$FIX/calib_marvel_local_theme" --json > "$TMP/k6.json"
assert "calib riverpod marvel: AnimatedTheme light/dark is not an app theme (no DS-005)" "$TMP/k6.json" "'DS-005' not in ids and d['stats']['themes'] == 1"
run "$FIX/calib_wonderous" --json > "$TMP/k7.json"
assert "calib wonderous: transparent hex and illustration art are not DS-001" "$TMP/k7.json" "'DS-001' not in ids"
assert "calib wonderous: pill radius 99 skipped, radius 10 still DS-004" "$TMP/k7.json" "[f['line'] for f in of('DS-004')] == [10]"
run "$FIX/calib_lichess" --json > "$TMP/k8.json"
assert "calib lichess: private padding constants in a widget file are not a scale" "$TMP/k8.json" "'DS-003' not in ids"
assert "calib lichess: static Color helper skipped, instance Color field is DS-011" "$TMP/k8.json" "[(f['line'], f['evidence'].split(':')[0]) for f in of('DS-011')] == [(12, 'GeneralPrefsState.boardAccent')]"
assert "calib lichess: primary-constructor extension found (DS-006 TP)" "$TMP/k8.json" "files('DS-006') == ['lib/src/styles/styles.dart']"
assert "calib lichess: copyWith(extensions: unresolved) means no DS-005" "$TMP/k8.json" "'DS-005' not in ids"
assert "calib lichess: forwarded brightness is not DS-009, a branch is" "$TMP/k8.json" "files('DS-009') == ['lib/src/widgets/side_indicator.dart']"
run "$FIX/calib_samples_m3demo" --json > "$TMP/k9.json"
assert "calib samples m3 demo: app root resolving ThemeMode.system is not DS-009" "$TMP/k9.json" "files('DS-009') == ['lib/src/buttons.dart']"

[ $fail = 0 ] && echo "ALL flutter-design-system TESTS PASSED" || echo "flutter-design-system: SOME TESTS FAILED"
exit $fail
