# Benchmark: with skills vs without

This is a small, reproducible benchmark of what the skills change. Read the
limitations before quoting the numbers.

## Setup (2026-10-17)

- **Agent and model:** OpenCode 1.18.30 with `opencode/big-pickle`, a free
  OpenCode Zen model. Deliberately *not* Claude, to test the "any agent" claim.
- **Toolchain:** Flutter 3.47 / Dart 3.13 on macOS.
- **Runs:** each task × configuration ran **twice**, on a fresh copy of the
  fixture.
- **Isolation:** every run used a fresh `HOME`, so no globally installed
  skills leaked in.
  - **Baseline:** the agent sees no skills.
  - **Skills:** the suite is installed with
    `install.sh --project <copy> --agent agents`, and the prompt adds "Use the
    installed agent skills."

## Tasks

| Task | Fixture | Ground truth |
|---|---|---|
| **T1 review**: "Review this Flutter app and list every real problem with file:line and severity." | MVN/Riverpod shop app | 12 planted issues (architecture, errors, security, navigation, forms, i18n, UI), plus 3 MVN decoys that look wrong but are correct |
| **T2 architecture**: "Is this architecture correct? List violations." | bloclibrary-style weather app | 2 planted violations, plus 6 decoys that follow bloclibrary conventions |
| **T3 write**: "Add a login feature that calls POST /login and stores the returned token, following this project's architecture." | MVN app | Scored by the suite's checkers on the result (security, architecture, error handling) and by `dart analyze` |

## Results

### T3: writing code

| | Token stored in | Security findings | Architecture | Errors (high/medium) | Analyzer |
|---|---|---|---|---|---|
| Baseline r1 / r2 | `SharedPreferences` ×2 | **1 high each** (SEC-001) | 0 | 0 | clean |
| Skills r1 / r2 | `flutter_secure_storage` ×2 | **0** | 0 | 0 | clean |

### T1: review

| | Recall (12 planted) | Extra claims* | MVN decoys flagged | Time |
|---|---|---|---|---|
| Baseline (mean of 2) | 92% (10/12, 12/12) | 10 | 0.5 | ≈ 8.5 min |
| Skills (mean of 2) | 96% (12/12, 11/12) | 17 | **0** | ≈ 50 min |

\* Extra claims are issues we didn't plant. On reading, most are plausible
real minor issues; some aren't defects.

### T2: Bloc architecture judgement

| | Recall (2 planted) | Claims contradicting bloclibrary |
|---|---|---|
| Baseline (mean of 2) | 2/2 | 0 |
| Skills (mean of 2) | 2/2 | 1.5 |

**Fixed after this run.** The 1.5 contradicting claims were the agent
repeating low-severity checker hits, all of them idiomatic in bloclibrary's
own `flutter_weather`:
- a page importing another feature's page to navigate
- the settings page reading the weather bloc
- `ThemeCubit` importing `material.dart` for `Color`

`arch_check` no longer reports these. The canonical `flutter_weather` example
and this fixture now produce only the 2 real violations, and both are pinned
by the regression fixture `calib_bloc_weather`. This table is from the run
*before* the fix. It hasn't been re-run since.

## What to take from it

- **Where the skills clearly help:** writing secure code by default. Both
  skill runs stored the token correctly, and both baseline runs didn't.
- **Review:** recall is about the same, and the skills avoided the MVN
  false alarm. But they produced more extra findings and took far longer on
  this free model, because the orchestrator runs many reviewer passes.
- **No help, or worse:** one Bloc case. It was a calibration bug, fixed
  above.

## Limitations

- N=2 per cell, with one free model. Run-to-run variance is large: the
  baseline T1 recall varied from 10/12 to 12/12.
- The fixtures and the ground truth were written by the suite's authors, and
  the planted issues match rules the checkers know. T1 therefore mostly tests
  whether the agent runs the tools and reports what they find.
- T3 is scored by the suite's own checkers.
- The grader parses free text heuristically: ±3 lines plus a category
  keyword. See `grade.py`.
- No severity scoring.

## Re-run it

```bash
cd bench
./run.sh t1 skills 1                       # one isolated run; also: t2|t3, baseline|skills
N=2 PAR=4 MODEL=opencode/big-pickle ./all.sh   # the full matrix
python3 grade.py summary runs/             # grade everything (add --json)
AGENT_CMD='claude -p' ./run.sh t3 skills 1     # try another agent CLI
```

- `SUITE_DIR` defaults to this repository. Point it elsewhere to benchmark
  another version of the suite.
- T3's `dart analyze` step needs `flutter pub get`, plus `build_runner` for
  the MVN fixture.
- Raw grades from the run above are in `results-2026-10-17-opencode-big-pickle.json`.
- PRs with runs on other agents and models are very welcome.
