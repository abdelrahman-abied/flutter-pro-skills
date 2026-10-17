---
name: flutter-architecture
description: Identify, judge and write Flutter app architecture - MVVM (Flutter guide), MVN (Model-View-Notifier with Riverpod), Clean Architecture, the repository pattern, Bloc/Cubit, MVC, and Riverpod, Provider, GetX or setState state. Detects the pattern (bundled checker), then judges code by THAT pattern's own rules, because they disagree (MVVM view models may call repositories, MVN notifiers go through use cases, Bloc forbids bloc-to-bloc). Reports dependency-rule violations and structural anti-patterns (logic in widgets, god view models, leaky repositories, boolean-soup state, service locators). Use it whenever the user asks about architecture, layers, folder structure, "where should this code go", "is this a good structure", one bloc or notifier calling another, refactoring existing code into layers, or choosing a pattern. To generate a new feature's files, use flutter-feature-scaffold.
license: MIT
metadata:
  author: abdelrahman-abied
  version: "1.4.0"
  suite: flutter-pro-skills
---

# Flutter architecture

This skill answers three questions about a Flutter codebase: *which architecture
is this?*, *does the code follow that architecture's own rules?*, and *how should
new code be shaped so it fits?*

The central idea: **an anti-pattern is relative to the pattern.** The common
Flutter architectures disagree on real points, and a reviewer who applies one
pattern's rules to another pattern's code produces noise:

- The Flutter team's MVVM guide lets a view model call repositories directly and
  treats use cases as optional. MVN forbids a Notifier from touching a
  repository; it goes through a use case.
- MVN sanctions notifier→notifier links via `ref.watch(otherProvider)` inside
  `build()`. Bloc says no bloc should know about any other bloc.
- A pass-through use case is ceremony in MVVM and prescribed structure in MVN.

So detect first, then judge against the pattern you detected.

## Workflow

### 1. Detect the architecture

Look for a **declared** architecture first. It beats inference (precedence rule 1):
your agent's project instructions file (`AGENTS.md`, `CLAUDE.md`, `GEMINI.md`,
`.cursor/rules/…`, `.github/copilot-instructions.md`), a README section, or an
ADR folder.

Then run the bundled checker. It is read-only, stdlib-only Python and needs no
`pub get`:

```bash
python3 -I <skill-dir>/scripts/arch_check.py <project-root>            # text report
python3 -I <skill-dir>/scripts/arch_check.py <project-root> --json     # profile + violations as JSON
python3 -I <skill-dir>/scripts/arch_check.py <project-root> --profile mvn       # declared pattern wins
python3 -I <skill-dir>/scripts/arch_check.py <project-root> --files changed.txt # diff review
```

Full CLI: `arch_check.py <project-root> [--json] [--files <file-with-relative-paths>]
[--profile auto|mvn|mvvm|bloc|mvc|getx|provider|riverpod|setstate] [--max <n>]`.
`--files` still builds the whole import graph over `lib/` but only *reports*
violations in the listed files. `--max` caps example locations per rule in text
mode (default 5). Exit `0` means a report was produced (findings never fail the
run); exit `2` is a usage error such as a missing `pubspec.yaml`. To share one
run with other checkers, save `--json` output to a file (`--json > arch.json`);
that file is the complete profile, including `files[]` (layer, role, feature per
file; roles include `repository`, `barrel` and `di`, and generated files are
already left out).

Text output has two sections:

```text
== ARCHITECTURE PROFILE
  presentation: mvn
  confidence: medium
  clean_architecture: true
  ...
  signals: dependency: flutter_riverpod, riverpod_annotation; 2 files under */presentation/notifier/; ...

== ARCHITECTURE VIOLATIONS
  [ARCH-005] ui-depends-on-data-source (high) x3 — A view imports a transport/data-source; ...
      lib/features/movie/presentation/view/movie_view.dart:4  import 'package:dio/dio.dart';
      ... 1 more
  suppressed: 2 (see --json)
```

Read `profile.confidence` and `profile.signals` before trusting the label. On
`low` confidence, a mixed codebase, or if you can't run Python, read
`references/detect.md` and classify by hand. It explains every signal and how to
handle codebases that are migrating between patterns.

### 2. Load the matching pattern reference

| `presentation` / flags | Read |
|---|---|
| `mvvm` | `references/mvvm.md` |
| `mvn` | `references/mvn.md` |
| `bloc` | `references/bloc.md` |
| `mvc`, `getx` | `references/mvc.md` (GetX specifics also in `references/state-management.md`) |
| `provider`, `riverpod`, `setstate`, `unknown` | `references/state-management.md`, then the closest pattern above |
| `clean_architecture: true` | also `references/clean-architecture.md` |
| `repository_pattern: true` | also `references/repository-pattern.md` |

Every reference has an allowed-dependency matrix, the canonical folder layout,
how state and side effects flow, and a "reviewing a … codebase" checklist.

### 3. Judge

1. **Confirm each script hit by reading the code.** The checker sees imports and
   regexes, not intent. Mark a finding `confirmed` only after you have read it.
   Drop false positives quietly; each rule's entry lists its known ones (find it
   from the index, `references/anti-patterns.md`, or with
   `grep -rn '^### <ID>' references/`).
2. **Respect the profile column.** Every rule in `references/anti-patterns.md`
   says where it applies and where it doesn't. If the rule doesn't apply to the
   detected pattern, it isn't a finding, however much it would be one elsewhere.
3. **Read for what the script can't see.** The `AP-*` entries (boolean-soup
   state, two sources of truth, leaky repositories, side effects in provider
   `build`, pass-through use cases …) need judgment. Walk the pattern's review
   checklist.
4. **Grade severity by consequence**, using the suite scale: High is a bug now
   or a violation that defeats the pattern's core guarantee; Medium hurts
   maintainability, testability or performance; Low is a local consistency fix;
   Info is a trade-off, not a defect.

### 4. Report

Return findings in the suite's finding format, so the `dart-flutter-review`
skill can merge and de-duplicate them:

```markdown
### [HIGH] View talks to Dio directly
- id: ARCH-005
- where: lib/features/movie/presentation/view/movie_view.dart:4
- evidence: `import 'package:dio/dio.dart';` and `Dio().get('/trending')` in build-triggered code
- rule: MVN: views render state only; I/O goes View → Notifier → UseCase → Repository → Source (flutter-architecture › mvn.md)
- why: the call can't be faked in tests, re-runs on rebuilds, and bypasses the repository's error mapping
- fix: |
    Move the call into MovieSource, expose it through MovieRepository and a use case,
    and have MovieNotifier call the use case; the view only watches movieProvider.
- confidence: confirmed
```

IDs are `ARCH-0xx` (import graph), `ARCH-1xx` (code pattern) or `AP-<slug>`
(judgment). Group by severity. Report a pattern-wide problem **once**, with a
few example locations, not once per file. Open with one line naming the
detected architecture and its confidence, so the reader knows which rulebook
you used.

## The patterns at a glance

| | Flutter MVVM | MVN | Bloc | Clean Architecture | MVC (incl. GetX) |
|---|---|---|---|---|---|
| Canonical source | docs.flutter.dev/app-architecture | the MVN spec (its author) | bloclibrary.dev | R. C. Martin | none for Flutter (mvc_pattern, GetX docs) |
| Logic role | `XViewModel` (ChangeNotifier, or any state lib) | `XNotifier` (`@riverpod`, extends `_$X`) | `XBloc` / `XCubit` | use case + presenter/controller | `XController` |
| View → logic | one view ↔ one view model | `ref.watch(xProvider)` | `BlocBuilder`/`context.read` | via adapter | controller / `Obx` |
| Logic → repository directly | **yes** (the norm) | **no**, through a use case | **yes**, injected repos | no, through a use case | yes |
| Use cases | optional, add when needed | **required** (one intent each) | optional (a domain layer, if any) | **required** | rare |
| Logic → other logic | not described; avoid | **allowed**: `ref.watch` in `build()` | **forbidden**: bloc-to-bloc | n/a | avoid |
| Repo → repo | never | never | never | never | never |
| One-time effects | listener on the VM or a `Command` | `ref.listen` in the view's `build` | `BlocListener` | presenter decides | `Get.snackbar`, `ever` workers |
| State shape | immutable models + VM fields / Commands | `sealed` state, `final` variants | `sealed` subclasses or class + status enum | entities + view models | `.obs` fields |
| Strength of rules | "recommendations, not steadfast rules" | spec ("binding") | recommendations; bloc-to-bloc "should not" | principle | convention |

Every pattern agrees on the core: widgets don't do I/O, the domain doesn't
depend on data or UI, repositories don't know about each other, state is
immutable, and dependencies are injected rather than reached for.

## Precedence when sources disagree

1. **The project's own decisions**: its lint config, its project instructions
   file, its declared architecture, and conventions used consistently in the
   code. A consistently applied local convention isn't a finding.
2. **The pattern's canonical source**: MVN → the MVN spec; Bloc →
   bloclibrary.dev; Riverpod → riverpod.dev; MVVM → the docs.flutter.dev
   architecture guide.
3. Effective Dart.
4. Flutter team guidance for apps.
5. The Flutter framework's internal style guide, only where the project
   already follows it.

Keep each rule at its source's strength. The Flutter guide calls itself
"guidelines, not steadfast rules"; Bloc's naming and state-modelling pages are
"simply recommendations". Don't report a recommendation as a violation.

## When not to flag

- **Small apps.** A two-screen app with `setState` and one service class is not
  under-architected. Don't demand a domain layer, use cases, or interfaces for
  types with one implementation and no tests (`AP-premature-domain-layer`,
  `AP-interface-for-everything`). The Flutter guide calls the domain layer
  optional and says to add use cases "only when needed".
- **The pattern sanctions it.** Notifier→notifier `ref.watch` in MVN or
  Riverpod; a pass-through use case in MVN; a view model calling a repository
  in MVVM; GetX controllers holding `TextEditingController`s; `BlocProvider`
  creating a bloc with `context.read<Repo>()` in a page widget.
- **The composition root.** `main*.dart`, `app/`, `di/`, `injection/`,
  `router/` may import every layer. That's their job.
- **Generated code** (`*.g.dart`, `*.freezed.dart`, `*.gr.dart`, `*.mocks.dart`,
  `*.config.dart`, `lib/generated/`, l10n output).
- **Suppressed hits.** `// arch-ignore: ARCH-005 <reason>` (line) and
  `// arch-ignore-file: ARCH-005 <reason>` (file) are the project's decision.
  Question a suppression only if its reason is wrong.
- **Mixed codebases.** Judge each feature by its own pattern and report the
  inconsistency once (see `references/detect.md`).
- **Taste.** Feature-first vs layer-first, `Screen` vs `Page`, `freezed` vs
  hand-written equality are choices, not defects, unless the project mixes them.

## Writing new code

- **Follow the detected pattern exactly**, including folder names, suffixes
  and the DI mechanism. Copy the shape of the nearest existing feature. A
  second vocabulary for the same role (a `ViewModel` in an MVN app, a
  `Controller` next to Blocs) is worse than either one alone.
- **Keep the dependency direction** of that pattern (see its matrix). When in
  doubt: views → logic → (use cases) → repositories → services/sources, and the
  domain imports nothing from data or UI.
- **Model state as a `sealed` hierarchy** or `AsyncValue` with an exhaustive
  `switch` expression, unless the pattern or project uses a single state class
  with a status enum (Bloc allows both).
- **Put one-time effects where the pattern says**: `ref.listen`,
  `BlocListener`, a `Command` listener. Never a `showDialog` bool in state.
- **Refactoring a feature into layers**: move I/O out of widgets into a
  service/source first, wrap it in a repository that returns domain models,
  then move logic into the pattern's logic class. Each step is shippable on
  its own. Don't refactor the whole app to a new pattern in the same change.

## Choosing a pattern (nothing detected, or a new app)

Start small and add layers when they pay for themselves.

| Situation | Suggest |
|---|---|
| Prototype, 1–3 screens, little shared state | `setState` + a service class. Extract a repository when a second screen needs the data |
| Typical app, team new to architecture | Flutter MVVM: views, `ChangeNotifier` view models, repositories, services, `provider` for DI (the Flutter team's default) |
| Team already on Riverpod, wants strict layering and codegen | MVN (load the `mvn` skill to scaffold) |
| Event-heavy flows, audit trail, team that likes explicit events | Bloc (Cubit for simple state) |
| Large app, several teams, complex client-side business rules | Clean Architecture layering (domain/data/presentation per feature) under any of the above |

Don't recommend switching an existing app's pattern unless it is causing
concrete harm. Migration cost is real, and a consistent "imperfect" pattern
beats a half-migrated "better" one.

## CI gate (fail PRs only on new violations)

`scripts/arch_check.py` has a CI mode. `--write-baseline <file>` records
today's violations once, and `--baseline <file> --ci --fail-on high` then
exits 1 only for violations that are **new** relative to that baseline. The
baseline's keys are line-number independent, so moving code doesn't break it.
The suite's GitHub Action (`uses: abdelrahman-abied/flutter-pro-skills@v1`)
wraps this. For setup, read `../dart-flutter-review/references/ci.md`.

## Related skills

Cross-skill references assume the suite is installed as sibling folders. If
your agent doesn't auto-load skills, read the path given. If a sibling is
missing, carry on with this skill and say which check you skipped.

- **`dart-naming`** for role-naming tables (`*ViewModel`, `*Notifier`,
  `*Bloc`, event/state names, file names). This skill doesn't repeat them.
  Fallback: `../dart-naming/SKILL.md` and `../dart-naming/references/naming.md`.
- **`flutter-ui-practices`** for widget-level concerns: lifecycle and
  `dispose`, `BuildContext` across `await`, rebuild cost, and the Flutter
  team's recommendation table with priorities. Fallback:
  `../flutter-ui-practices/references/flutter-ui.md`.
- **`dart-flutter-review`** runs the full review: the analyzer, this skill's
  checker (through `review.sh`), parallel reviewers, and the merged report.
  Fallback: `../dart-flutter-review/SKILL.md`.
- **`mvn`** (the MVN author's scaffolding skill; some agents list it as
  `mvn-architect:mvn`) for generating MVN features. If it isn't installed,
  `references/mvn.md` carries the spec's rules and layout.

## References

| File | Read it when |
|---|---|
| `references/detect.md` | classifying by hand, low confidence, mixed or migrating code |
| `references/anti-patterns.md` | the catalog index: every `ARCH-*` and `AP-*` with severity, profiles and detection, linked to its entry. Read it first |
| `references/anti-patterns/<group>.md` | the full entries (bad/good code, fix, false positives), one file per group: `dependency-rule`, `presentation`, `state`, `data-and-repositories`, `di-and-globals`, `over-engineering`, `pattern-specific`. `grep -rn '^### <ID>' references/` lands on one |
| `references/mvvm.md` | Flutter team MVVM: views, view models, commands, repositories, services |
| `references/mvn.md` | Model-View-Notifier with Riverpod codegen |
| `references/bloc.md` | Bloc and Cubit |
| `references/clean-architecture.md` | domain/data/presentation, the dependency rule, use cases |
| `references/repository-pattern.md` | repositories and services in any pattern |
| `references/mvc.md` | MVC in Flutter (`mvc_pattern`, `fluttery_framework`, GetX-style controllers) |
| `references/state-management.md` | how Riverpod, Provider, GetX, ChangeNotifier and setState map onto the patterns |
