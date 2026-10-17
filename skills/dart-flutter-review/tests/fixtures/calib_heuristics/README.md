Regression fixture for `scripts/heuristics.py grep`, built from the minimal repros in the
phase-3 calibration reports (K1 compass_app/Habo, K2 bloc examples, K3 riverpod/hiddify/lichess).
Never analysed or compiled; `tests/run.sh` asserts on the grep output only.

- `lib/guards/`: canonical-app shapes that were false positives. Nothing in a guard file may be
  reported (except `noise-word-type` on `HabitsManager`, a different heuristic).
- `lib/downgrade/`: real but weaker smells, reported under a low-severity variant id.
- `lib/tp/`: true positives that must keep firing after the fixes.
