---
name: dart-flutter-best-practices
description: Hub for writing idiomatic Dart and Flutter code - Effective Dart, the official lints, the language features your SDK allows and the project's own conventions, verified with `dart format` and `dart analyze`. Use it whenever you write or refactor general Dart code, a package or CLI, ask if code is idiomatic, or set up lints, `analysis_options.yaml` or formatting. When one concern dominates, load that specialist instead - `flutter-feature-scaffold`, `dart-naming`, `flutter-ui-practices` (widgets), `flutter-performance` (jank), `flutter-architecture` (layers), `flutter-testing`, `flutter-error-handling`, `flutter-secure-defaults` (auth), `flutter-navigation`, `flutter-forms`, `flutter-i18n`, `flutter-persistence`, `flutter-networking` (API), `flutter-platform-integration` (native), `flutter-design-system`, `flutter-accessibility`, `flutter-release` (ship), `dart-flutter-review` (reviews).
license: MIT
metadata:
  author: abdelrahman-abied
  version: "1.4.0"
  suite: flutter-pro-skills
---

# Dart & Flutter best practices (hub)

This is the entry point of the `flutter-pro-skills` suite. It holds the rules
that apply to *all* Dart code, the WRITE workflow, and team setup. It sends
everything more specific to a sibling skill, so you load only what the task
touches.

The aim is code that reads as if one careful author wrote it. That means it
agrees with the official guidance, it fits the project it lives in, and it
avoids the bugs idiomatic Dart rules out by construction (unawaited futures,
swallowed errors, `late` fields read too early).

## Precedence when sources disagree

1. **The project's own decisions**: its lint config, its project instructions
   file (`AGENTS.md`, `CLAUDE.md`, `GEMINI.md`, `.cursor/rules/…`,
   `.github/copilot-instructions.md`), its declared architecture, and any
   convention it uses consistently. Effective Dart's first theme is *be
   consistent*. A "correct" rule applied to half a codebase makes it worse. If
   the project disables a lint on purpose, it has decided, so don't argue
   with it file by file.
2. **The chosen pattern's canonical source**: MVN follows the `mvn` spec by its
   author, Bloc follows bloclibrary.dev, Riverpod follows riverpod.dev, and
   MVVM follows the docs.flutter.dev architecture guide.
3. **Effective Dart**: the baseline for all Dart code. The full checklist is
   in `references/effective-dart.md`.
4. **Flutter team guidance for apps**, from docs.flutter.dev and `flutter_lints`.
5. **The Flutter framework's internal style guide.** It was written for
   contributors to the framework, and several of its rules contradict Effective
   Dart (`kConstant` prefixes, 100-column lines). Follow it only where the
   project already does.

Keep each rule at the strength of its source keyword. **DO/DON'T** means
near-always, **PREFER/AVOID** means unless there's a good reason, and
**CONSIDER** depends on context. A PREFER deviation is not a bug.

## Route to the right skill

Load the sibling skill for the part of the task in front of you. If your agent
doesn't auto-load skills, read the fallback path, which is relative to this
skill's folder because the suite installs as sibling folders. If a sibling is
missing, say so and carry on with Effective Dart and this file.

| The task involves | Load | Fallback path |
|---|---|---|
| Naming or renaming anything: classes, methods, booleans, files, providers, blocs, events | `dart-naming` | `../dart-naming/SKILL.md` |
| Widgets, `State` lifecycle and `dispose`, `BuildContext` across `await`, `build()` cost, lists, theming, accessibility, widget tests | `flutter-ui-practices` | `../flutter-ui-practices/SKILL.md` |
| Where code belongs: layers, folders, MVVM / MVN / Bloc / Clean Architecture / repositories, state management, anti-patterns | `flutter-architecture` | `../flutter-architecture/SKILL.md` |
| Creating a new feature, screen or module in the project's own architecture (generates the files, dry run first) | `flutter-feature-scaffold` | `../flutter-feature-scaffold/SKILL.md` |
| Writing or reviewing tests, what to test per layer, untested code, flaky tests, mocks vs fakes, goldens | `flutter-testing` | `../flutter-testing/SKILL.md` |
| try/catch, exceptions vs `Result`, failures, error states, "spinner never stops", crash reporting, global handlers | `flutter-error-handling` | `../flutter-error-handling/SKILL.md` |
| Reviewing, auditing or critiquing code, a diff or a PR | `dart-flutter-review` | `../dart-flutter-review/SKILL.md` |
| Tokens, credentials, auth, storage, HTTP clients, logging of sensitive data, WebViews, "is this secure", secure defaults while writing | `flutter-secure-defaults` | `../flutter-secure-defaults/SKILL.md` |
| go_router, deep links, redirects/guards, passing route arguments, url_launcher | `flutter-navigation` | `../flutter-navigation/SKILL.md` |
| Forms, validation, TextFormField, focus, submit/double-submit, password/OTP inputs | `flutter-forms` | `../flutter-forms/SKILL.md` |
| Localization, ARB/gen-l10n, plurals, dates/numbers, RTL and Arabic | `flutter-i18n` | `../flutter-i18n/SKILL.md` |
| Jank, slow scrolling, excess rebuilds, `const`, `RepaintBoundary`, lazy lists and slivers, isolates and `compute`, image decode size, DevTools profiling | `flutter-performance` | `../flutter-performance/SKILL.md` |
| Local storage and caching: Drift, sqflite, Hive/Isar, shared_preferences, offline-first and sync, migrations | `flutter-persistence` | `../flutter-persistence/SKILL.md` |
| API calls and the HTTP client: Dio/http/retrofit setup, timeouts, interceptors, DTOs and JSON, pagination, cancellation, retry, WebSockets | `flutter-networking` | `../flutter-networking/SKILL.md` |
| Native code: platform channels, Pigeon, FFI, platform views, writing a plugin, runtime permissions, background isolates | `flutter-platform-integration` | `../flutter-platform-integration/SKILL.md` |
| Design tokens, `ThemeData`/`ColorScheme`, `ThemeExtension`, shared components, dark mode, raw colours or sizes in feature code | `flutter-design-system` | `../flutter-design-system/SKILL.md` |
| Accessibility: `Semantics`, labels, tap targets, contrast, text scale, focus order, screen-reader tests | `flutter-accessibility` | `../flutter-accessibility/SKILL.md` |
| Shipping the app: flavors and environments, signing, versioning, store requirements, CI/CD (GitHub Actions, Codemagic, Fastlane) | `flutter-release` | `../flutter-release/SKILL.md` |
| Deep security audit: obfuscation, pinning, RASP, attestation, build hardening | `flutter-security-audit` (separate repo, if installed) | `../flutter-security-audit/SKILL.md`; otherwise say it isn't installed |

Writing a Flutter feature usually touches several of these. Scaffold it in
the project's pattern, then use architecture for where the code goes, UI for
the widgets, naming for the new types, error handling for its failure paths,
and testing for its tests.

## First: read the project

Spend a minute on these before you write a line.

- **`pubspec.yaml` and the SDK constraint.** The *lower bound* of
  `environment: sdk:` sets the package's language version, and that decides
  which features compile. The installed SDK doesn't decide it. Features gated
  by language version:

  | Feature | Needs |
  |---|---|
  | Records, patterns, `switch` expressions, class modifiers (`sealed`, `final`, `base`, `interface`) | ≥3.0 |
  | Extension types | ≥3.3 |
  | Digit separators (`1_000_000`) | ≥3.6 |
  | Wildcard `_` parameters and locals; the tall formatter style; `formatter:` options in `analysis_options.yaml` | ≥3.7 |
  | `formatter: trailing_commas: preserve`; null-aware elements (`[?maybeItem]`) | ≥3.8 |
  | Dot shorthands (`.start`, `.new()`, `.all(8)` where the type is known) | ≥3.10 |
  | Private named initializing formals (`Foo({required this._client})`, preferred over `: _client = client`) | ≥3.12 |

  Also note what kind of package it is (Flutter app, Dart package or CLI) and
  which state-management, DI and routing packages it depends on.
- **`analysis_options.yaml`.** Check which set is included (`flutter_lints`,
  `lints/recommended`, `very_good_analysis` or custom), which rules are added
  or disabled, the `formatter: page_width`, and the `exclude:` globs.
  Generated code (`*.g.dart`, `*.freezed.dart`) is never yours to edit or judge.
- **The project instructions file** (see Precedence). Look for a declared
  architecture line such as `Architecture: Clean + MVN`, and for
  team conventions.
- **Two or three neighbouring files.** Check `var` vs `final` locals (either is
  fine, but pick one), relative vs `package:` imports, feature-first vs
  layer-first folders, role suffixes (`Screen`/`Page`/`View`,
  `Notifier`/`ViewModel`/`Bloc`), and how errors and results are modelled.

## WRITE mode: generating or changing code

1. **Match before you invent.** New code should look like it belongs: use the
   project's state management, folder structure and suffixes. Match its
   *conventions*, not its *defects*. If the neighbouring code leaks
   controllers or does I/O in widgets, don't copy that. Write the new code
   correctly and mention the existing problem.
2. **Load the sibling for what you touch** (routing table above). The
   architecture skill decides *where* code goes, and the UI skill covers
   lifecycle and `build()`. The naming skill applies whenever you introduce a
   public name, because names are the one thing tools can't fix later without
   breaking callers.
3. **Write it idiomatically the first time.** Hold the code to the judgment
   rules below as you write. Default lints don't catch them. Use the newest
   features the SDK constraint allows when they make the code clearer, and
   never use features it doesn't allow.
4. **Verify with the toolchain, then fix only what you introduced.**
   ```bash
   dart format <files you touched>      # respects formatter: page_width
   dart analyze <files or dir>          # `flutter analyze` is equivalent in a Flutter app
   ```
   Fix every error, warning and lint *your change* introduced. Don't reformat
   or "fix" unrelated files: that buries the real change in noise and makes the
   diff hard to review. If a lint must stay, write `// ignore: rule_name`
   followed by the reason. An unexplained ignore is itself a finding. If
   `dart` isn't available, say that you couldn't verify.
5. **Don't over-document.** Add `///` docs to public APIs whose names don't
   say everything. Never write a comment that restates the name
   (`/// The user id.` on `userId`). See *Documentation* in
   `references/effective-dart.md`.
6. **Never hand-edit generated files.** Change the source and run
   `dart run build_runner build -d` (or tell the user to).

## Dart judgment rules (no default lint catches these)

Check these by reading. Each maps to a row in `references/effective-dart.md`,
so grep it for the keyword (`late`, `FutureOr`, `getter`, `catch`) when you
want the exact guideline and its strength.

- Don't use `late` when you need to check whether the field was initialised.
  Use a nullable field instead.
- Don't store what you can calculate. Use a getter, not a field that must be
  kept in sync.
- Return `Future<void>`, never plain `void`, from async members that produce no
  value. Avoid `FutureOr<T>` as a return type.
- Don't return a nullable `Future`, `Stream` or collection. Return an empty
  one instead.
- Throw `Error` subclasses only for programmer mistakes, and `Exception`s for
  runtime failures. Never catch `Error`. Don't write a bare `catch` without
  `on` unless you rethrow or report the error.
- Don't create a class with only static members. Use top-level functions and
  constants, or an `abstract final class` as a namespace.
- Use class modifiers (`final`, `base`, `interface`, `sealed`) to say how a
  public class may be extended or implemented. Model closed sets of variants
  as `sealed` with an exhaustive `switch`.
- Avoid positional `bool` parameters (`render(true)`); make them named.
- Override `hashCode` whenever you override `==`. Don't give mutable classes
  value equality.
- Annotate types on public APIs and on variables without initialisers. Don't
  annotate obvious locals.
- Every `Future` is awaited, returned, or wrapped in `unawaited(...)` on
  purpose. A dropped future loses its error.

## Naming and Flutter UI live in sibling skills

- Naming rules (casing, `get`/`k`/`I` prefixes, booleans, callbacks, files, role suffixes) are in `dart-naming`.
- Widget rules (dispose, `context.mounted`, pure `build()`, widget classes over helper methods, lazy lists, `MediaQuery.sizeOf`) are in `flutter-ui-practices`.
- Deep dives that widget code often needs: `flutter-performance` (jank and rebuilds), `flutter-design-system` (tokens and themes), `flutter-accessibility` (semantics, targets, contrast), `flutter-persistence` (local storage and caching).
- Architecture rules (layering, which layer may call which, per-pattern conventions) are in `flutter-architecture`.
- Review procedure, severity and report format are in `dart-flutter-review`.
- If one of these isn't installed, apply Effective Dart and say which guidance was unavailable.

## Setup for teams

Offer these when the user wants a project to follow the conventions every
time. Don't add them silently.

- **Lint set: `assets/analysis_options.yaml`.** This is `flutter_lints` plus the
  Effective Dart rules that aren't on by default, with each rule annotated by
  the guideline it enforces. For a pure Dart package, change the include to
  `package:lints/recommended.yaml` and drop the rules marked `[flutter]`.
  Suggest it when the project has no `analysis_options.yaml` or an empty one.
  `dart-flutter-review` also runs it as an informational EXTRA LINTS pass.
- **Project instructions: `assets/AGENTS-snippet.md`.** This is a short block
  for `AGENTS.md`. The other agents' files (`CLAUDE.md`, `GEMINI.md`,
  `.cursor/rules/`, `.github/copilot-instructions.md`) can include it or
  copy it. Fill in its `Architecture:` line: reviewers judge the code against
  the declared pattern rather than guessing it.
- **Format on write: `scripts/format-dart-hook.sh`** (optional). It runs
  `dart format` on one edited `.dart` file and skips generated code. It never
  blocks and always exits 0. It accepts a file path as `$1`, which works for
  any hook system that can pass a path and for git pre-commit, or hook JSON
  `{"tool_input":{"file_path":…}}` on stdin, for example a Claude Code
  post-edit hook. Setup examples are in the script header.

## Files in this skill

| File | Use it when |
|---|---|
| `references/effective-dart.md` | You're writing non-trivial Dart, or you're unsure about a guideline. It has ~150 rows, one per guideline, each tagged with the lint that enforces it or *judgment*. Grep it for a keyword, or `grep -n '^##'` to find a section, rather than reading it whole |
| `assets/analysis_options.yaml` | Setting up or tightening lints |
| `assets/AGENTS-snippet.md` | Making every agent in a repo follow these conventions |
| `scripts/format-dart-hook.sh` | Enforcing formatting automatically |
