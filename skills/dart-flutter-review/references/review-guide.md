# Reviewing existing Dart / Flutter code

## Contents
1. Procedure: scope, mechanical pass, judgment pass, calibration
2. Severity rubric
3. Report template

This is the reference for the `dart-flutter-review` skill. Its SKILL.md runs the
phases (and the parallel reviewers). This file holds the procedure detail, the
severity rubric and the report template. Load it by section: run
`grep -n '^#' references/review-guide.md` and read only what you need.

A good review tells the author the few things that matter most, why they matter,
and exactly how to fix them. A dump of 300 lint lines teaches nothing. Let the
toolchain own the mechanical layer, and spend your attention on what tools
can't see.

## Procedure

### 1. Establish scope and baseline
- **Diff/PR review**: get the changed files (`git diff --name-only <base>...HEAD -- '*.dart'`).
  Judge only changed lines and what they directly affect (callers of a changed
  signature, the `dispose` of a newly added controller). Pre-existing problems
  in untouched code go in a short "Outside this change" note, at most.
- **Whole project or feature review**: list `lib/`, read `pubspec.yaml` and
  `analysis_options.yaml`, and identify the architecture and state solution. Take
  the declared architecture from the project instructions file (`AGENTS.md`,
  `CLAUDE.md`, `GEMINI.md`, `.cursor/rules/…`, `.github/copilot-instructions.md`)
  if it has one, and otherwise from the detected profile in the ARCHITECTURE
  section. Then
  prioritise: the files with the most logic (view models, notifiers, repositories),
  the biggest widgets, and anything touching async, I/O or lifecycles. For more
  than about 40 files, sample each layer instead of reading everything, and say
  that you sampled.
- Exclude generated code (`*.g.dart`, `*.freezed.dart`, `*.gr.dart`, `*.mocks.dart`,
  `lib/generated/`, l10n output) unless the generator config is the subject.

### 2. Mechanical pass
```bash
bash <skill-dir>/scripts/review.sh <project-root>                 # whole project
bash <skill-dir>/scripts/review.sh <project-root> --diff main     # only files changed vs main
bash <skill-dir>/scripts/review.sh <project-root> --profile mvn   # declared architecture beats detection
```
`<skill-dir>` is the `dart-flutter-review` folder. Other flags: `--no-extra`
skips the stricter lint pass, `--no-arch` the architecture pass, `--no-tests`,
`--no-errors`, `--no-security` (both security passes), `--no-audit`,
`--no-nav`, `--no-forms`, `--no-i18n`, `--no-perf`, `--no-persist`, `--no-net`, `--no-ds`
and `--no-a11y` the sibling passes (or one
`--skip <list>`), and `--max <n>` sets how many example locations each rule
prints (default 5). Generated files (`arch_check.py`'s `files[]` decides for
`lib/`) are never in scope.
Exit code 0 means the report was produced, even when it has findings. Exit
code 2 means a usage or environment error: no `pubspec.yaml`, or `dart` not
on PATH.
The script reports, without modifying anything:
- **Format**: files `dart format` would change.
- **Analyzer**: errors, warnings, infos, grouped by rule with counts (using the
  project's own lint config). If generated files are missing, the codegen
  cascade is one `collapsed:` line ("run build_runner"), not thousands of
  errors. An analyzer crash is one `analyzer crashed (…)` line, and an SDK
  outside the pubspec constraint skips the section with the reason.
- **Auto-fixable**: what `dart fix --dry-run` would fix.
- **Effective Dart extra lints** (opt-in, run *only for information*): the same
  files analysed with `../dart-flutter-best-practices/assets/analysis_options.yaml`,
  so you can see what the stricter set would flag. Present these as a suggestion
  to adopt the set, not as violations. The project didn't opt into them.
  If the hub skill isn't installed, the section prints a `skipped` line.
- **Architecture** (`== ARCHITECTURE PROFILE` and `== ARCHITECTURE VIOLATIONS`,
  from `../flutter-architecture/scripts/arch_check.py`): the detected profile
  (presentation pattern, Clean Architecture, repositories, layout, state
  management, confidence and the signals behind it), then import-graph and
  code-pattern violations grouped by `ARCH-0xx`/`ARCH-1xx` rule, with
  `file:line` and evidence. These are exact matches against the pattern's rules,
  and they still need reading before you report them. A `// arch-ignore:` hit
  appears only in the `suppressed` count. In diff mode, violations are limited
  to the changed files, while the graph is still built over all of `lib/`. If
  the architecture skill isn't installed, the section is one `skipped` line.
- **Sibling checkers**: `== TEST GAPS`/`== TEST SMELLS`, `== ERROR HANDLING`,
  `== SECURITY DEFAULTS`, `== NAVIGATION`, `== FORMS` and `== I18N`, each
  from its skill's script (`[TEST-…]`, `[ERR-0xx]`, `[SEC-0xx]`, `[NAV-0xx]`,
  `[FORM-0xx]`, `[I18N-0xx]` groups), and `== SECURITY AUDIT` from the
  separate `flutter-security-audit` skill's `scan.sh` (MASVS/CWE-tagged
  candidates; absence checks are project-wide). Each is one `skipped` line
  when its skill isn't installed. None of them fails CI.
- **Heuristic candidates** (`[CANDIDATE]` lines): greps for judgment-level smells.
  Every candidate must be confirmed by reading the code before it becomes a
  finding. Some will be false positives. Drop them quietly.

### 3. Judgment pass (read the code)
Work in this order. It's the order of the cost of getting it wrong.

1. **Correctness and lifecycle**: undisposed controllers and subscriptions,
   `context`/`setState` after `await` without a mounted check, futures created
   in `build`, unawaited futures that hide errors, `catch` blocks that swallow,
   catching `Error`, `late` fields that may be read before they are set, `!` on
   values that can really be null, `==` without `hashCode`, mutable classes with
   value equality.
2. **API design and naming** (`dart-naming` › `naming.md`, Effective Dart *Design*): misleading
   names, `getX()` methods, positional bools, nullable collection or Future returns,
   `dynamic` leaking into APIs, static-only classes, missing class modifiers on
   public classes in packages.
3. **Architecture** (the `flutter-architecture` skill, judged against the
   profile): layer and dependency-rule violations, logic in widgets, god view
   models or notifiers, leaky repositories, boolean-soup state, service locators
   in UI, and over-engineering. **Judge by the declared or detected pattern's own
   rules**, because the patterns disagree. An MVVM view model may call a
   repository directly, while an MVN notifier goes through a use case. A
   pass-through use case is prescribed under MVN and only Info elsewhere. Bloc
   forbids bloc-to-bloc dependencies, and Riverpod's `ref.watch(otherProvider)`
   is sanctioned. When the profile's confidence is `low` or `unknown`, report
   only pattern-independent problems (I/O in widgets, domain depending on data,
   cycles) and say the pattern couldn't be determined.
4. **Structure and Flutter practice** (`flutter-ui-practices` ›
   `flutter-ui.md`): giant `build` methods, helper-method widgets, eager lists,
   broad `MediaQuery.of`, rebuild scope.
5. **Style and docs**: comments that restate the code, missing public docs (in
   packages), import ordering, and anything else the formatter or lints would
   handle. Usually you can just say "run `dart fix --apply && dart format .`".

### 4. Calibrate before reporting
- **Respect the project's decisions.** A rule disabled in `analysis_options.yaml`,
  or a convention used consistently across the codebase (`kConstants`, `userId`,
  `final` everywhere), is not a finding. Inconsistency *within* the project is.
  Neither is a deliberate architecture choice that the project instructions file
  declares. Judge the code against that choice, and at most add an Info note
  on its trade-offs.
- **Keep each rule at its own strength.** A PREFER/CONSIDER deviation is at most
  low severity, unless it causes a concrete bug.
- **Show evidence.** Each finding cites `file:line` and quotes or describes the
  code. "Might leak" isn't a finding. "`_controller` is created in `initState`
  (L24) and there is no `dispose` override" is one.
- **Merge duplicates.** The same issue in 12 places is one finding with a list
  of locations.
- **Analyzer output that `dart fix` can't apply is not "Mechanical".** Errors,
  warnings like `unused_field`, and lints with no fix (`use_build_context_synchronously`,
  `cancel_subscriptions`) go into the judgment findings. Analyzer errors are
  High and warnings are usually Medium. Merge each one into the finding it
  belongs to (for example, `unused_field` on an undisposed controller goes in
  the dispose finding). Only what `dart fix --apply` / `dart format` resolves goes in **M**.
- **Info is not a defect.** Observations and trade-offs (pass-through use
  cases outside MVN, a domain layer that's premature for a small app, an
  interface with one implementation and no fake) go under Info. Don't let them
  pad the defect count.
- **Deliver the report in chat** unless the user asked for a file. If they did,
  save it where they said.

## Severity rubric

| Severity | Meaning | Typical examples |
|---|---|---|
| **High** | A bug now or under ordinary use: crash, leak, lost error, wrong UI. Or an architecture violation that defeats the pattern's core guarantee | Missing `dispose`/`cancel`; `context` after `await` unguarded; `catch (e) {}` around I/O; `==` without `hashCode`; future created in `build` causing repeat requests; analyzer **errors** |
| **High** (architecture) | The dependency rule is broken where the pattern relies on it | I/O or HTTP inside a widget (ARCH-101, ARCH-005); domain importing data or presentation (ARCH-001, ARCH-002); data importing presentation (ARCH-004) |
| **Medium** | Hurts maintainability, testability or performance noticeably, or is a costly API to change later | Misleading public names; `getX()` async methods; positional bools in public APIs; eager `ListView(children:)` on unbounded data; `dynamic` in APIs; analyzer **warnings** |
| **Medium** (architecture) | A layering leak or structure that makes the code hard to test or change | Notifier/view model importing a concrete source or I/O package (ARCH-007); view importing a repository (ARCH-008); MVN notifier bypassing the use case (ARCH-012); `BuildContext`/navigation in logic (ARCH-102); god files (ARCH-103); mutable or global state (ARCH-105, ARCH-106); leaky repository (ARCH-107); feature cycles (ARCH-015); god view model, boolean-soup state (AP-) |
| **Low** | Idiom or consistency; easy, local fix | Helper-method widgets in small screens; `MediaQuery.of` for size; missing `const` on big static subtrees; doc wording; lint **infos** |
| **Low** (architecture) | Local structural smell, cheap to fix | Service locator in UI (ARCH-104); concrete-only repository (ARCH-108); ephemeral controllers in providers (ARCH-109); event flags in state (ARCH-111); cross-feature internal import (ARCH-014); MVN naming drift (ARCH-112) |
| **Info** | Observations and trade-offs, not defects | Pass-through use cases outside MVN (AP-passthrough-usecase); a premature domain layer in a small app; an interface with a single implementation and no fake; the profile couldn't be determined |
| **Mechanical** | Fully fixed by tools | Everything `dart fix --apply` and `dart format` resolve. Always **one** collapsed finding |

The defaults for architecture rules come from the rule catalog, and each
`ARCH-` line printed by the script carries its severity. Adjust a rule
up or down only with a reason tied to this project. For example, ARCH-103
on a file that is 90% generated-looking data tables is Low.

## Report template

Use this structure. Keep it scannable: the author should be able to act from the
summary table alone.

````markdown
# Dart/Flutter review: <scope>

**Scope:** <diff vs main: 9 files | whole project: lib/ 64 files (sampled 28)>
**Toolchain:** Dart <x.y> · lints: <flutter_lints 6 + 4 custom> · format: <3 files unformatted>
**Architecture:** <declared: Clean + MVN (AGENTS.md) | detected: mvvm, feature-first, confidence medium>
**Coverage:** <mechanical ✓ · architecture ✓ · UI ✓ · Dart/naming ✓ · testing ✓ · errors ✓ · security: not installed>
**Verdict:** <one sentence, e.g. "Two lifecycle bugs to fix before merge; the rest is polish.">

| # | Severity | Finding | Location |
|---|---|---|---|
| 1 | High | `AnimationController` never disposed | lib/ui/home/home_screen.dart:31 |
| 2 | Medium | ... | ... |
| 3 | Info | ... | ... |
| M | Mechanical | `dart fix --apply` resolves 42 issues (unnecessary_this ×18, prefer_final_fields ×9, …) | 17 files |

## Findings

### 1. `AnimationController` never disposed (High)
**Where:** `lib/ui/home/home_screen.dart:31`
**Rule:** Flutter: dispose what you create (`flutter-ui-practices` › flutter-ui.md §1)
**Why it matters:** the controller keeps ticking and holds the `State` after the
screen is popped, so memory and CPU are lost on every visit.
**Fix:**
```dart
@override
void dispose() {
  _controller.dispose();
  super.dispose();
}
```

### 2. ...

## Mechanical fixes
Run `dart fix --apply && dart format .` (or `--diff`-scoped paths). Top rules: ...

## Worth adopting (optional)
- Enabling <rules> from the Effective Dart set would also flag N issues; see `dart-flutter-best-practices/assets/analysis_options.yaml`.

## Outside this change (diff reviews only, optional)
- ...
````

After the report, **offer** (don't perform) the next step: apply the mechanical
fixes, fix the High items, or a specific finding. If the user accepts, make the
changes, rerun `scripts/review.sh` on the touched files, and report the
before/after counts.
