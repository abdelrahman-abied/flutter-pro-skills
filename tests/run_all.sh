#!/usr/bin/env bash
# Run every check in the repo: spec validation, then each skill's own test suite.
# Works without the Flutter SDK (skills skip SDK-dependent parts).
set -u
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
fail=0

echo "== validate SKILL.md files"
python3 -I "$ROOT/tests/validate_skills.py" || fail=1

echo
echo "== install.sh"
bash "$ROOT/tests/test_install.sh" || fail=1

for t in "$ROOT"/skills/*/tests/run.sh; do
  [ -f "$t" ] || continue
  echo
  echo "== $(basename "$(dirname "$(dirname "$t")")")"
  bash "$t" || fail=1
done

echo
echo "== shell syntax"
for s in "$ROOT"/install.sh "$ROOT"/skills/*/scripts/*.sh; do
  bash -n "$s" && echo "PASS bash -n ${s#$ROOT/}" || { echo "FAIL bash -n ${s#$ROOT/}"; fail=1; }
done

echo
[ $fail = 0 ] && echo "ALL PASSED" || echo "SOME CHECKS FAILED"
exit $fail
