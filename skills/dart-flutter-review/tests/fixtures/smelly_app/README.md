Test fixture for `skills/dart-flutter-review/tests/run.sh`. Do not "fix" it.

- Files under `lib/core/`, `lib/features/cart/data/sources/` and
  `lib/features/cart/presentation/view/cart_view.dart` contain planted smells that
  `scripts/heuristics.py grep` must report.
- Every other file is a regression guard for a false positive that was fixed
  after running the heuristics on a real app; the heuristics must report
  nothing for them.
