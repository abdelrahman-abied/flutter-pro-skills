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
| **T5 write** (added 2026-10-18): "Add a product gallery feature: load products page by page from GET /products?page=N … with infinite scroll … on tablets and desktop show a list-detail layout … look right in dark mode and work with a screen reader. Follow this project's architecture." | the T3 MVN app | Every checker; only findings the agent added count (`new_*`) |
| **T4 write** (added 2026-10-18): "Add a products screen that loads GET /products … in a scrollable list with each product's image, name, price and a favourite icon button, with pull-to-refresh, following this project's architecture." | the T3 MVN app | Scored like T3, plus the performance, design-system and accessibility checkers, minus the fixture's own findings |

## Results

### Sonnet with the skills vs Opus without them (Claude Code, 2026-10-18, v1.7.0)

Can a cheaper model with the skills match a stronger one without them?
`AGENT=claude CLAUDE_MODEL=sonnet|opus`, N=2 per cell.

**T3, add login and store the token**

| | Token stored in | Security findings | Cost | Time |
|---|---|---|---|---|
| **Opus**, no skills | `SharedPreferences` ×2 | **SEC-001 high, both runs** | $2.1, $1.8 | 5, 4 min |
| Sonnet, no skills | `SharedPreferences` ×2 | **SEC-001 high, both runs** (plus FORM-003 low) | $1.0, $1.3 | 4, 5 min |
| **Sonnet + skills** | `flutter_secure_storage` ×2 | **0** | $5.5, $7.1 | 12, 20 min |

**T5, a paginated, adaptive, accessible gallery** (new findings only)

| | New findings | Tests written | Cost | Time |
|---|---|---|---|---|
| **Opus**, no skills | 0, 0 | 0, 12 | $3.6, $6.8 | 15, 17 min |
| Sonnet, no skills | PERF-004 (low) in both runs | 18, 4 | $5.0, $5.7 | 15, 18 min |
| **Sonnet + skills** | **0, 0** | 0, 3 | $5.3, $6.0 | 14, 13 min |

**What to take from it.**
- **The strongest result in the benchmark.** The most capable model,
  without the skills, stored the auth token in plain `SharedPreferences` in
  both runs. Sonnet with the skills stored it in secure storage in both runs,
  with zero security findings. Secure by default is the suite's main promise,
  and on this task neither model delivers it on its own.
- **On T5, Sonnet + skills matched Opus** (0 findings) at about the same cost.
  Without the skills, Sonnet decoded full-size images in the list both times.
- **The cost of the skills depends on the task.** On T5 the skills cost
  Sonnet almost nothing extra ($5.3–6.0 vs $5.0–5.7). On T3, where the work
  is small, they cost about 5× ($5.5–7.1 vs $1.0–1.3), because loading the
  skills is a fixed cost.
- **The Sonnet runs with the skills wrote few tests** (0 and 3). Both
  extended the existing feature instead of scaffolding one, so the
  scaffold's test checklist never applied. **Fixed after this run:** the
  hub's WRITE mode now asks for tests on any change.

Raw grades: `results-2026-10-18-claude-sonnet-vs-opus.json`.

### On Claude Code (Opus), 2026-10-18 (suite after the PASS PLAN and reading-budget changes)

`AGENT=claude`, N=2 per cell, the same fixtures and graders. The model is
much stronger than big-pickle, so this asks a different question: does the
suite still add anything when the agent is already good?

**T5, write a paginated, adaptive, accessible gallery**

| | New findings | Paginates / list-detail / analyzer | Tests written | Time | Cost |
|---|---|---|---|---|---|
| Baseline r1 / r2 | 0, 0 | yes / yes / clean | **0 and 12** | 15, 17 min | $3.6, $6.8 |
| Skills r1 / r2 | 0, 0 | yes / yes / clean | **43 and 37** | 22, 22 min | **$17.0, $18.3** |

**T1, review (12 planted issues, 3 MVN decoys)**

| | Recall | Extra claims | Decoys flagged | Time | Cost |
|---|---|---|---|---|---|
| Baseline r1 / r2 | 12/12, 12/12 | 8, 9 | 0, 1* | 5, 5 min | $2.0, $1.9 |
| Skills r1 / r2 | 12/12, 12/12 | 7, 13 | 0, 0 | 6, 8 min | $2.9, $3.3 |

\* As before, the matched claim is a real race-condition finding on the
decoy's line, not an objection to `ref.watch`.

**What to take from it.**
- **On a strong model the checkers find nothing to fix either way.** Opus
  writes clean, layered, accessible code on its own, so "0 findings" doesn't
  separate the configurations here.
- **The skills' measurable gain is tests and layering.** The skills runs
  wrote 3–4× as many tests (one baseline run wrote none), plus the full MVN
  layers (use cases), hence more files.
- **That gain costs about 3–4× on writing** ($17–18 vs $4–7), because the
  agent still loads about 7 skills and runs the checkers about 10 times. This
  is the next thing to cut.
- **Review is now close to baseline in time and cost** (6–8 vs 5 min, about
  1.5× the cost), down from about 3× the time on big-pickle before the PASS
  PLAN and quick mode, with the same 12/12 recall.
- **A grader fix:** `grade.py` now reads Claude Code's stream-json (the final
  `result`). Before that fix, every Claude review scored 0/12.

**After the cost cut** (`review.sh --findings-only` and the scaffold's
cross-cutting rules, commit `c30bcc0`), T5 with the skills, 2 more runs:

| | Cost | Time | Turns | Skills loaded | Checker runs | New findings | Tests |
|---|---|---|---|---|---|---|---|
| Skills before (r1 / r2) | $17.0, $18.3 | 22, 22 min | 148, 143 | 7, 7 | 11, 10 | 0 | 43, 37 |
| **Skills after (r3 / r4)** | **$13.8, $10.5** | 21, 18 min | 117, 95 | 6, 3 | **3, 2** | 0 | 28, 15 |
| **Skills, second cut (r5 / r6)** | **$14.8, $12.3** | 22, 22 min | 126, 114 | 5, 4 | 5, 4 | 1*, 0 | **29, 34** |
| Baseline (r1 / r2) | $3.6, $6.8 | 15, 17 min | 58, 90 | 0 | 0 | 0 | 0, 12 |

\* DS-003 (low): the agent added a spacing scale (`AppSpacing`), which turned
an existing `EdgeInsets.all(12)` into a finding. It's a side effect of
adding tokens, not new bad code.

The second cut (commit `6dcb7bb`) added a "stop reading here" note to six
specialist skills and a test checklist to the scaffold:
- **Tests came back:** 29 and 34, against 15 and 28 after the first cut.
- **Cost didn't fall further:** $12–15. With N=2 the spread between runs is
  as large as the change.
- **Across both cuts:** the average cost with the skills went from $17.6 to
  about $12.9 (−27%), with tests at 31 instead of 40, and every run kept 0
  bad findings and the full feature.
- **Still about 2–3× baseline.** That remains the price of the tests and the
  full layering the skills add on a strong model.

- **Cost fell 24–42%**, and checker runs fell from 10–11 to 2–3, with the same
  quality (0 findings, every feature).
- **The skills still cost about 2–3× baseline.** One run still loaded 6
  specialist skills: the prompt names dark mode and screen readers, and
  their descriptions match.
- **Fewer tests than before** (28 and 15 vs 43 and 37), but still more than
  baseline (0 and 12). The run that skipped `flutter-testing` wrote the
  fewest; the second cut below addresses it.

Raw grades: `results-2026-10-18-claude-code.json`.

### Re-run on 2026-10-18, second pass (suite v1.6.1: T1, T2 and the new T5)

Same agent, model and isolation, N=2 per cell, with the machine kept awake
(`caffeinate`), so these times are real.

**T1, review (12 planted issues, 3 MVN decoys)**

| | Recall | Extra claims | MVN decoys flagged | Time |
|---|---|---|---|---|
| Baseline r1 / r2 | 10/12, 12/12 | 6, 9 | 0, 0 | 10 min, 15 min |
| Skills r1 / r2 | **12/12, 12/12** | 18, 19 | 1*, 0 | 45 min, 30 min |

\* This "decoy" is a real race-condition finding on the same line (a stale
search response can overwrite a newer one). It doesn't object to `ref.watch`,
which is the decoy. The grader matches by line and keyword, so it can't tell
the difference.

**The trade-off.** The skills found everything both times, but they made
about twice the extra claims and took about three times as long. The review
orchestrator runs one reviewer pass per specialist, and this model runs them
one after another.

**T2, Bloc architecture (2 planted violations, 6 bloclibrary decoys)**

| | Recall | Claims contradicting bloclibrary |
|---|---|---|
| Baseline r1 / r2 | 2/2, 2/2 | 2, 1 |
| Skills r1 / r2 | 2/2, 2/2 | **0, 0** |

**T5, a paginated gallery with list-detail on tablets, dark mode and screen
readers** (new findings only, compared with the pristine fixture)

| | New findings | Paginates / list-detail | Time |
|---|---|---|---|
| Baseline r1 | ARCH-007 (medium), PERF-004 (low) | yes / yes | 29 min |
| Baseline r2 | PERF-004 (low) | yes / yes | 16 min |
| Skills r1 | — | **wrote no code** | 11 min |
| Skills r2 | — | **stalled** (the provider stopped answering) | killed after 57 min |

**T5 with the skills is inconclusive, but it found a real problem.** Run 1
read the skills, wrote a correct plan (pagination, two panes at ≥600 dp,
tests) and then stopped at "Proceed?". `flutter-feature-scaffold` told the
agent to "confirm the plan with the user before writing" unconditionally. In a
non-interactive run that means no code. **Fixed:** the skill now decides,
states its choices in one line, and writes (`--write` never overwrites). It
asks only when the architecture is genuinely ambiguous. A re-run of T5 with
the fix could not happen: the free provider stopped answering at all,
including a "reply with ok" probe. That leaves T5's skills cell to run again.

**Grader fixes in this pass:**
- T3–T5 report `new_*` counts: findings the agent added, not those already in
  the fixture.
- Summary lines such as "**Detected: Bloc** … no use cases — correct
  rulebook" are no longer read as claims, so they don't count as flagging a
  decoy.
- `confidence: high` is no longer read as a severity.

Raw grades: `results-2026-10-18b-opencode-big-pickle.json`.

### Re-run on 2026-10-18 (suite v1.4–v1.5, T3 and the new T4)

Same agent, model and isolation as below, N=2 per cell. **Wall-clock times
are not comparable in this run**: the machine slept during several runs, so
some report about 11 hours.

**T3, add login and store the token.** This reproduces the first run:

| | Token stored in | Security findings |
|---|---|---|
| Baseline r1 / r2 | `SharedPreferences` ×2 | **1 high each** (SEC-001; r1 also SEC-010) |
| Skills r1 / r2 | `flutter_secure_storage` ×2 | **0** |

**T4, a products screen with images and a favourite button per row** (scored
by the performance, design-system, accessibility, architecture and error
checkers). The fixture already has one low PERF-004 and one low A11Y-003 in
`product_tile.dart`. They are excluded below.

| | New findings in the agent's code | Lazy list | Analyzer |
|---|---|---|---|
| Baseline r1 | ARCH-007 (logic imports a concrete data source), ERR-001 (swallowed catch) | yes | clean |
| Baseline r2 | none | yes | clean |
| Skills r1 | none | yes | clean |
| Skills r2 | none; it also fixed the fixture's two existing lows | yes | clean |

**What to take from T4.** It barely separates the two configurations on this
model. The free model writes a lazy list with labelled buttons either way. The
only differences are one baseline run that broke a layering rule and swallowed
an error, and one skills run that cleaned up existing issues. T4 needs a harder
prompt to say more.

**A grader bug was fixed while scoring this run.** `grade.py` looked for the
checkers in an ignored `suite_snapshot/` folder. When that folder was missing,
every checker silently scored 0, which read as "clean". It now falls back to
this repository's `skills/`, and stops with an error if a checker is missing.
The first grading of this run was all zeros for that reason.

Raw grades: `results-2026-10-18-opencode-big-pickle.json`.

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
./run.sh t1 skills 1                       # one isolated run; also: t2|t3|t4|t5, baseline|skills
N=2 PAR=4 MODEL=opencode/big-pickle ./all.sh   # the full matrix (TASKS="t3 t4" for a subset)
python3 grade.py summary runs/             # grade everything (add --json)
./progress.sh runs/                        # live status per run: elapsed, idle, tool calls, files changed, STALLED?
AGENT=claude ./run.sh t5 skills 1          # Claude Code on your login (see the AGENT note in run.sh)
AGENT_CMD='some-agent --flag' ./run.sh t3 skills 1   # any other agent CLI
```

- `SUITE_DIR` defaults to this repository. Point it elsewhere to benchmark
  another version of the suite.
- T3's `dart analyze` step needs `flutter pub get`, plus `build_runner` for
  the MVN fixture.
- Raw grades from the run above are in `results-2026-10-17-opencode-big-pickle.json`.
- PRs with runs on other agents and models are very welcome.
