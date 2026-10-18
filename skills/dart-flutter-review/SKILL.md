---
name: dart-flutter-review
description: Review, audit or quality-check Dart/Flutter code, a diff, branch or PR and return one severity-ranked report with file:line evidence and a fix per finding. A read-only mechanical pass (format, analyzer, dart fix --dry-run, the suite's checkers, heuristic greps) is followed by parallel judgment passes (architecture, UI, idioms, naming, security, plus one per specialist such as tests, errors, i18n, performance, accessibility). Highs are verified and findings deduplicated. A CI mode and GitHub Action fail PRs only on new violations. Use it whenever someone asks to review, audit or sanity-check Dart/Flutter code, a branch, PR or codebase before merging, asks "what's wrong with this code" or wants a CI gate, even if they never say "review". Load it before reading the diff. If the request covers only one concern (only tests, only strings/RTL, only names), load that skill instead.
license: MIT
metadata:
  author: abdelrahman-abied
  version: "1.6.1"
  suite: flutter-pro-skills
---

# Dart & Flutter review (orchestrator)

A good review tells the author the few things that matter most, why they
matter, and exactly how to fix them. The toolchain owns the mechanical layer.
Your attention goes to what tools can't see, judged against the pattern the
project actually uses. This skill is **read-only** until the user asks for
fixes.

You run five phases: **0** scope and profile, **1** mechanical, **2** judgment
(in parallel when possible), **3** verify the Highs, **4** merge and report,
**5** offer fixes.

## What this skill uses

| File | Holds | Load |
|---|---|---|
| `scripts/review.sh` | The mechanical pass (calls `scripts/heuristics.py` and the architecture checker) | Run it, don't read it |
| `references/review-guide.md` | Procedure detail, calibration rules, severity rubric, report template | By section |
| `references/finding-format.md` | The exact shape every pass returns findings in, with examples | Before Phase 2 |
| `references/reviewer-prompts.md` | Self-contained prompts for each reviewer and the verifier | When you spawn sub-agents |
| `references/ci.md` | CI mode, the baseline flow and the GitHub Action | When asked for CI, a PR gate or a baseline |
| `scripts/ci_action.sh` | The GitHub Action's entry point (also runnable locally) | Run it, don't read it |

Sibling skills, each with a fallback path relative to this skill's folder:
- `flutter-architecture` (`../flutter-architecture/SKILL.md`): profile detection, per-pattern rules, the anti-pattern catalog, `arch_check.py`
- `flutter-ui-practices` (`../flutter-ui-practices/SKILL.md`): widgets, lifecycle, async/context, performance
- `dart-naming` (`../dart-naming/SKILL.md`): naming
- `dart-flutter-best-practices` (`../dart-flutter-best-practices/SKILL.md`): Effective Dart checklist (`../dart-flutter-best-practices/references/effective-dart.md`) and the stricter lint set
- `flutter-testing` (`../flutter-testing/SKILL.md`): test strategy per pattern, `test_gaps.py` (optional testing pass)
- `flutter-error-handling` (`../flutter-error-handling/SKILL.md`): error flow across layers, `check_errors.py` (optional errors pass)
- `flutter-secure-defaults` (`../flutter-secure-defaults/SKILL.md`): write-time security per layer, `check_secure_defaults.py` (security pass)
- `flutter-navigation`, `flutter-forms`, `flutter-i18n` (`../flutter-<x>/SKILL.md`): routing and deep links, forms and input, localisation and RTL, each with a `check_*.py` (optional passes)
- `flutter-performance`, `flutter-persistence`, `flutter-networking`, `flutter-design-system`, `flutter-accessibility`, `flutter-release`, `flutter-platform-integration`, `flutter-adaptive-layout`, `flutter-firebase` (`../flutter-<x>/SKILL.md`): jank and rebuilds, local storage and migrations, the API client layer, tokens and themes, semantics and contrast, flavors/signing/store/CI, channels/Pigeon/FFI/plugins, size classes/platform idioms, Firebase rules/init/FCM, each with a `check_*.py` (optional passes)
- `flutter-security-audit`: a separate skill by the same author (RASP, pinning, obfuscation, attestation, MASVS/CWE). When installed next to this one, `review.sh` runs its `scan.sh`, and the security pass loads it for depth

If a sibling is missing, run without it and name the gap on the report's
**Coverage** line. A partial review that says what it skipped beats a
confident one that silently didn't check.

**Load references by section.** Run `grep -n '^##' <file>` and read only the
sections the code touches. The suite's references total thousands of lines, and
reading them all wastes the context you need for the code.

## Phase 0: scope and profile

1. **Scope.** Decide whether this is a **diff** or a **project** review.
   - Diff: "review my PR / my changes / this branch". Get the files with
     `git diff --name-only --diff-filter=ACMR <base>...HEAD -- '*.dart'`, plus
     uncommitted and untracked files if the user means the working tree.
     Judge the changed lines and whatever they directly affect: callers of a
     changed signature, the `dispose` for a newly added controller.
   - Project or feature: "review the app / this feature / lib/". Cover every
     layer, and prioritise logic files, big widgets, and anything with async,
     I/O or lifecycles.
   - Ask only if you can't infer it.
2. **Profile.** Read `pubspec.yaml` (SDK constraint, state-management and DI
   dependencies) and `analysis_options.yaml` (what is enabled or disabled).
   Then read the project instructions file: `AGENTS.md`, `CLAUDE.md`,
   `GEMINI.md`, `.cursor/rules/…` or `.github/copilot-instructions.md`. Look for
   a **declared architecture** line (e.g. `Architecture: Clean + MVN`). A
   declared pattern beats detection. Map it to a profile value for
   `--profile`: `mvn`, `mvvm`, `bloc`, `mvc`, `getx`, `provider`, `riverpod`
   or `setstate`.
3. **Note conventions** from two or three files: k-constants, `var` vs
   `final`, `_onTap` handlers, suffixes. A convention used consistently is a
   project decision, not a finding.
4. **Size.** Count the non-generated `.dart` files in scope. That count
   decides parallel vs sequential in Phase 2. Never review generated code
   (`*.g.dart`, `*.freezed.dart`, `*.gen.dart`, `*.mocks.dart`, `lib/generated/`,
   l10n output, "GENERATED CODE" headers). `review.sh` takes the scope from
   `arch_check.py`'s `files[]`, so its file count is the one to use.

## Phase 1: mechanical pass

Run the script once and **save its output to a temp file**, because sub-agents
read it instead of re-running it:

```bash
out="$(mktemp "${TMPDIR:-/tmp}/dart-review.XXXXXX")"
bash <skill-dir>/scripts/review.sh <project-root> [--diff <ref>] [--profile <p>] > "$out" 2>&1
echo "$out"
```

`<skill-dir>` is this skill's folder. Flags: `--diff <ref>`, `--profile <p>`
(from Phase 0; it reaches every sibling checker), `--max <n>`, the CI flags
`--ci`, `--fail-on`, `--baseline` (see "CI mode" below), and skips:
`--no-extra`, `--no-arch`, `--no-tests`, `--no-errors`, `--no-security` (both
security sections), `--no-audit`, `--no-nav`, `--no-forms`, `--no-i18n`,
`--no-perf`, `--no-persist`, `--no-net`, `--no-ds`, `--no-a11y`, `--no-release`,
`--no-platform`, `--no-adaptive`, `--no-firebase`, or one
`--skip extra,arch,tests,errors,security,audit,nav,forms,i18n,perf,persist,net,ds,a11y,release,platform,adaptive,firebase`. `--findings-only` prints only the checker findings at low or above, plus
analyzer errors and warnings. Use it to check your own change once after
writing; it isn't meant for a review report. The script never
modifies the project. Exit code 0 means the report was produced, even with
findings. Exit code 2 means there's no `pubspec.yaml` or `dart` isn't on PATH.
Only `--ci` exits 1.

Sections (run `grep -n '^== ' "$out"` to find them):
- `CONTEXT`: SDK, lint include, scope. A pub workspace member gets a
  `packages:` line (resolved at the workspace root); that is fine. A
  `WARNING: no .dart_tool` line means packages aren't resolved. Suggest
  `flutter pub get` / `dart pub get` and rerun, because otherwise ANALYZER is
  mostly unresolved-import noise. Don't report that noise. A `WARNING: pubspec
  sdk constraint …` line means the installed SDK can't analyse this project,
  so ANALYZER, AUTO-FIXABLE and EXTRA LINTS are skipped: say so on Coverage.
- `FORMAT`, `AUTO-FIXABLE`: these become **one** collapsed Mechanical finding.
- `ANALYZER`: the project's own lint config. Fold each item into a judgment
  finding. `codegen: N generated file(s) missing` plus `collapsed: M error(s)`
  means build_runner hasn't run: report **one** finding ("run build_runner"),
  never the cascade. `analyzer crashed (…)` means no analyzer results; name it
  on Coverage.
- `EXTRA LINTS`: the stricter set the project has *not* adopted. Mention it once
  under "Worth adopting", and never report it as violations.
- `ARCHITECTURE PROFILE` / `ARCHITECTURE VIOLATIONS`: the detected profile and
  `ARCH-0xx`/`ARCH-1xx` hits. If the line says `skipped`, the architecture
  skill isn't installed.
- `TEST GAPS` / `TEST SMELLS`: from `flutter-testing`'s `test_gaps.py`,
  untested units ranked by architecture priority, and smells in `test/`.
  Always whole-project, even in diff mode.
- `ERROR HANDLING`: `[ERR-0xx]` groups from `flutter-error-handling`'s
  `check_errors.py`, limited to the diff in diff mode.
- `SECURITY DEFAULTS` (`[SEC-0xx]`), `NAVIGATION` (`[NAV-0xx]`), `FORMS`
  (`[FORM-0xx]`), `I18N` (`[I18N-0xx]`), `PERFORMANCE` (`[PERF-0xx]`),
  `PERSISTENCE` (`[PERSIST-0xx]`), `NETWORKING` (`[NET-0xx]`), `FIREBASE` (`[FIRE-0xx]`), `PLATFORM` (`[PLAT-0xx]`), `DESIGN SYSTEM` (`[DS-0xx]`), `ADAPTIVE LAYOUT` (`[ADAPT-0xx]`),
  `ACCESSIBILITY` (`[A11Y-0xx]`): the sibling checkers, limited to the diff in
  diff mode. `RELEASE` (`[REL-0xx]`) reads Gradle, Xcode, plist and CI files,
  so it always covers the whole project and says so in diff mode. `FIREBASE`
  does the same, because it reads the security rules files.
- `SECURITY AUDIT`: `flutter-security-audit`'s `scan.sh`, regrouped
  (`[NET-NO-PINNING] (high) … (absence check)`). These are candidates.
  Absence checks are project-wide, and they're omitted in diff mode.
- Any of these says `skipped` when its skill isn't installed, and `error` if
  its script failed. No failure stops the run.
- `CANDIDATES`: heuristic `[CANDIDATE]` lines. Each must be confirmed by
  reading before it becomes a finding. When ERROR HANDLING ran, the
  `swallowed-catch` candidate keeps only its count and says "see ERROR
  HANDLING": those catches are ERR-001 hits, so report each one once, there.
  Likewise `eager-children-map` says "see PERFORMANCE" when that checker
  ran, and `hardcoded-color` says "see DESIGN SYSTEM". `opacity-widget` keeps
  its locations: drop it only where `PERF-005` reports the same line.

If `dart` isn't available, still run the architecture checker on its own
(`python3 -I <skill-dir>/../flutter-architecture/scripts/arch_check.py <project-root>
[--files <list>] [--profile <p>]`, it needs only Python), and say that the
analyzer and format passes were skipped. The other checkers (`test_gaps.py`,
`check_errors.py`, `check_secure_defaults.py`, `check_navigation.py`,
`check_forms.py`, `check_i18n.py`, `check_performance.py`,
`check_persistence.py`, `check_networking.py`, `check_firebase.py`, `check_platform.py`, `check_adaptive.py`, `check_release.py`, `check_design_system.py`, `check_accessibility.py`)
need only Python, and `scan.sh` only bash
(CLIs in `references/ci.md` › Local equivalents).

## Phase 2: judgment passes

There are four core dimensions and fourteen optional ones. Each returns findings
in the shape given in `references/finding-format.md`.

| Pass | Loads | Starts from | IDs |
|---|---|---|---|
| (a) Architecture | `flutter-architecture` | `ARCHITECTURE` sections + profile | `ARCH-0xx`, `ARCH-1xx`, `AP-` |
| (b) Flutter UI / lifecycle / performance | `flutter-ui-practices` | lifecycle and build candidates; context/async lints | `UI-`, `LINT:` |
| (c) Dart idioms + naming | `effective-dart.md` from the hub + `dart-naming` | naming and error-handling candidates; analyzer | `ED-`, `NAME-`, `LINT:` |
| (d) Security | `flutter-secure-defaults`; `flutter-security-audit` for depth | `SECURITY DEFAULTS`, `SECURITY AUDIT` | `SEC-0xx`, `SEC-` |
| (e) Testing (optional) | `flutter-testing` | `TEST GAPS` / `TEST SMELLS` | `TEST-` |
| (f) Errors (optional) | `flutter-error-handling` | `ERROR HANDLING`; owns catches when it runs | `ERR-0xx`, `ERR-` |
| (g) Navigation (optional) | `flutter-navigation` | `NAVIGATION` | `NAV-0xx`, `NAV-` |
| (h) Forms (optional) | `flutter-forms` | `FORMS` | `FORM-0xx`, `FORM-` |
| (i) I18n (optional) | `flutter-i18n` | `I18N` | `I18N-0xx`, `I18N-` |
| (j) Performance (optional) | `flutter-performance` | `PERFORMANCE` | `PERF-0xx`, `PERF-` |
| (k) Persistence (optional) | `flutter-persistence` | `PERSISTENCE` | `PERSIST-0xx`, `PERSIST-` |
| (l) Design system (optional) | `flutter-design-system` | `DESIGN SYSTEM` | `DS-0xx`, `DS-` |
| (m) Accessibility (optional) | `flutter-accessibility` | `ACCESSIBILITY` | `A11Y-0xx`, `A11Y-` |
| (n) Networking (optional) | `flutter-networking` | `NETWORKING` | `NET-0xx`, `NET-` |
| (o) Release (optional) | `flutter-release` | `RELEASE` | `REL-0xx`, `REL-` |
| (p) Platform integration (optional) | `flutter-platform-integration` | `PLATFORM` | `PLAT-0xx`, `PLAT-` |
| (q) Adaptive layout (optional) | `flutter-adaptive-layout` | `ADAPTIVE LAYOUT` | `ADAPT-0xx`, `ADAPT-` |
| (r) Firebase (optional) | `flutter-firebase` | `FIREBASE` | `FIRE-0xx`, `FIRE-` |

**Follow the `== PASS PLAN`** at the end of the mechanical output: it is the
cheapest way to a fast review. It lists the core passes, every optional pass
whose checker found something at low or above (`run:`), and the ones with
nothing to confirm (`skip:`). Run the `run:` passes. Skip the `skip:` ones
unless the user asked about that area or reading the code turns up something
in it: each skipped pass saves a full reading pass, and its checker already
looked. The plan's `mode:` line says quick or parallel (below).

The security pass (d) is core: "secure by default" means every review looks.
If neither security skill is installed, run it from the template's own
checklist and say so on Coverage. Run each optional pass when its skill is
installed (its section isn't `skipped`) or the user asks about that area; for
(g)–(r), also only when the code has it (a router, forms, localisation or
user-facing strings, widgets, local storage, theme code, HTTP calls, platform
folders or CI config, platform channels or FFI, widgets for (q), a Firebase dependency for (r)). If a skill is missing, leave the pass out and name the
gap on the Coverage line. The idioms pass (c) still covers swallowed catches
when (f) doesn't run, and the UI pass (b) still covers l10n/RTL when (i)
doesn't, and lists, images, colours and semantics when (j), (l) or (m) don't.

**In parallel, when you can.** Use parallel sub-agents if your agent can spawn
them (for example Claude Code's Agent/Task tool, Codex sub-agents, or another
agent's equivalent) **and** the scope is big enough: roughly more than 15
files, or the user asked for a deep or thorough review.
1. Write the file list to a temp file. You already have the mechanical output
   path.
2. Fill in the templates from `references/reviewer-prompts.md` verbatim: A, B,
   C and D (security), plus E (testing), F (errors), G (navigation), H (forms),
   I (i18n), J (performance), K (persistence), L (design system), M
   (accessibility), N (networking), O (release), P (platform integration)
   Q (adaptive layout) and R (Firebase) when they apply, as above.
   Use absolute paths.
3. Spawn every reviewer **at once**, each **read-only**, and wait for all of
   them. Each prompt says: confirm by reading, return text only, write no
   files, edit no code.
4. If a reviewer fails or returns something malformed, run that dimension
   yourself. Don't drop it silently.

**Quick mode, otherwise** (`mode: quick` in the plan: 15 files or fewer, or
no sub-agents). Don't run the templates one by one. Make **one combined
pass** instead:
1. Confirm every `run:` group and every High or Medium `[CANDIDATE]` by
   opening the file at that line. Drop what reading disproves.
2. Read the files in scope once, in this order: lifecycle and UI bugs, the
   architecture rules of the detected pattern, security, then error flow.
   Note only what is at least Medium, or a Low with a one-line fix.
3. Load a sibling skill only to settle a finding you are unsure of, and read
   only the section the rule points at, not the whole reference.

Use the same finding format, so Phase 4 works the same way. For more than ~40
files without sub-agents, sample each layer and say that you sampled.

## Phase 3: verify every High

A false High costs the author more than a missed Low, so give each High finding
**one adversarial check** that tries to disprove it. The check looks for a
dispose in a base class or mixin, `ref.onDispose`, ownership handed elsewhere,
a mounted guard, a project decision, or a pattern that sanctions the code.
Spawn a verifier per High, or batch small ones, using Template V in
`references/reviewer-prompts.md`, if sub-agents are available. Otherwise do the
check yourself and argue against your own finding. Drop **DISPROVED**
findings. Apply **DOWNGRADE** results with the stated reason. Keep
**CONFIRMED** findings, and mark them `confidence: confirmed`.

## Phase 4: merge and report

1. **Collect** all pass outputs and build the one Mechanical line from FORMAT and
   AUTO-FIXABLE ("`dart fix --apply` resolves 42 issues across 17 files:
   unnecessary_this ×18, …").
2. **Dedupe by (file, line, root cause).** The same root cause in several
   places is one finding with a location list. When passes overlap, keep the
   **most specific ID**. A numbered `ARCH-` rule beats an `AP-` slug. A
   `UI-`/`ED-`/`NAME-` slug that names the root cause beats a `LINT:` code
   that only shows the symptom. An `ERR-` ID beats `ED-swallowed-catch` and
   the `swallowed-catch` candidate for the same catch. A checker ID beats the
   reading-level slug for the same file and line: `SEC-0xx` beats a `scan.sh`
   ID (cite it in `rule:`), `I18N-010` beats `UI-l10n` (hard-coded UI string),
   `I18N-012` beats `UI-rtl` (physical-direction geometry), `PERF-` beats
   `UI-eager-list`/`UI-opacity`/`UI-image-decode-size`/`UI-rebuild-scope`/
   `UI-blocking-ui-isolate`, `DS-` beats `UI-hardcoded-style`, `A11Y-` beats
   `UI-a11y`, storage tokens stay `SEC-001` over any `PERSIST-` slug, transport
   security stays `SEC-` over `NET-` (NET owns timeouts, client reuse,
   retry policy, pagination and cancellation), and `NAV-`/`FORM-`
   beat `UI-` for routing and form fields. Navigation inside logic stays
   `ARCH-102`. Fold the others into `rule:` and `evidence:`.
3. **Calibrate** with `references/review-guide.md` › "Calibrate before
   reporting". Respect the project's decisions and keep each rule at its own
   strength. Judge architecture against the declared or detected profile.
   **Analyzer output that `dart fix` can't apply is not Mechanical**: it goes
   into the judgment finding it belongs to. Info items are trade-offs, not
   defects.
4. **Rank**: High, then Medium, Low, Info, Mechanical. Within one severity,
   put the widest blast radius first: most locations, public API, hot path.
5. **Report** with the template in `references/review-guide.md` › "Report
   template". Include the Scope, Toolchain, Architecture and Coverage lines,
   a one-sentence verdict, and the summary table. Give full write-ups for the
   High and Medium findings, and let a table carry the long tail.
   **Deliver it in chat** unless the user asked for a file.

## Phase 5: offer fixes, don't apply them

End by offering the next step without taking it. You can (a) apply the
mechanical layer with `dart fix --apply && dart format <scope>`, (b) fix the
High items, or (c) fix specific findings. Renaming a public member of a
published package is breaking, so say so and offer a `@Deprecated`
forwarding member.

If the user accepts, make the changes. Then rerun `scripts/review.sh` on the
touched files: `--diff HEAD` covers uncommitted and untracked changes. Report
the before/after counts per section and any finding the change didn't
resolve.

## CI mode

For a PR gate rather than a conversation, run the mechanical pass in CI mode:

```bash
bash <skill-dir>/scripts/review.sh <project-root> --ci [--fail-on high|medium|low] [--baseline <file>] [--diff <ref>]
```

It exits 1 when architecture violations at or above `--fail-on` (default
`high`) are **new** versus the baseline, or when the analyzer reports errors
(only counted after `pub get`, and never for codegen cascades, an analyzer
crash or an SDK the pubspec excludes). Test gaps, error handling, security
(including `scan.sh`, whatever its own exit code), navigation, forms, i18n,
performance, persistence, networking, design system, accessibility, release, platform, adaptive layout, firebase and candidates are informational and never fail the run. A `== CI RESULT` section explains the
verdict, and with `$GITHUB_STEP_SUMMARY` set it appends a Markdown summary
(section counts and top findings). The baseline comes from
`arch_check.py --write-baseline <file>`, and its keys ignore line numbers, so
unrelated edits don't invalidate it.

The repository root's `action.yml` wraps this as a GitHub Action
(`uses: abdelrahman-abied/flutter-pro-skills@v1`). With `flutter: false` it
runs only the architecture check and needs nothing but Python. Read
`references/ci.md` for the workflow YAML, the baseline adoption flow and the
equivalent local commands. CI mode is a gate, not a review: when someone asks
why CI failed, run the normal phases on the reported files.

## Lessons from real runs

- **Sub-agents return text, not files.** Some environments block sub-agents
  from writing files. Ask for the findings in the reply, and do any file
  writing yourself.
- **One mechanical run.** Sub-agents read the saved output. If four agents
  re-run `dart analyze`, the review takes four times as long and they may
  disagree.
- **Candidates are not findings.** Heuristic greps have false positives by
  design: tear-off disposal, generic dispose loops, ownership hand-offs.
  Open the file before you report.
- **Mechanical means `dart fix`/`dart format` can fix it.** Errors, warnings
  and lints with no fix belong in judgment findings.
- **Deliver in chat** unless the user asked for a file.
- **Read references by section.** Grep the headings. Don't read every file
  in full.
