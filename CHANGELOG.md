# Changelog

All notable changes to this project are documented here. The project follows
[Semantic Versioning](https://semver.org). Rule IDs (`ARCH-0xx`, `ERR-0xx`,
`SEC-0xx`, …) are part of the public contract: renaming or removing one is a
breaking change.

## [Unreleased]

### Fixed

- **The scaffold no longer stops to ask before writing.**
  `flutter-feature-scaffold` told agents to "confirm the plan with the user
  before writing" every time. In the benchmark, an agent wrote a correct plan
  and then waited at "Proceed?", producing no code. The skill now decides,
  states its choices and writes (it never overwrites). It asks only when the
  architecture is genuinely ambiguous, and in non-interactive runs it takes
  the neighbouring features' pattern and lists its assumptions.
- **Faster reviews.** `review.sh` ends with a `== PASS PLAN`. It lists
  which optional reviewer passes have findings to confirm and which have
  nothing, so they can be skipped. Its mode line says quick (15 files or
  fewer, or no sub-agents) or parallel. In quick mode the review makes one
  combined pass instead of running the templates one by one. On the
  `smelly_app` fixture, 9 of the 14 optional passes are skipped.
- **One check after writing.** `review.sh --findings-only` runs every
  checker and prints only what is left to fix: about 25 lines instead of 200
  on `smelly_app`. The scaffold and the hub now tell agents to check once with
  it, not checker by checker. The scaffold also carries the screen's
  cross-cutting rules (lists, images, theme, semantics, layout, network,
  text), so a standard feature doesn't need six specialist skills loaded.
  Measured on Claude Code (T5): cost $17–18 → $10.5–13.8 per run, and
  checker runs 10–11 → 2–3, with 0 findings either way.
- **Stop reading early for scaffolded features.** Six specialist skills
  open with a "Writing a standard feature?" note, and the scaffold's
  checklist lists the tests to write. Measured on T5: 29 and 34 tests (15
  and 28 after the first cut) at $12–15 a run. Across both cuts the cost with
  the skills fell from $17.6 to about $12.9 on average (−27%).
- **A smaller reading budget when writing.** The hub tells agents to read a
  sibling's SKILL.md and only the reference section it points at. When the
  scaffold generates a feature, there's no need to pre-load the
  performance, design-system, accessibility, networking or persistence
  skills: the templates already pass those checkers, which run once at the
  end.
- **Benchmark on Claude Code.** `grade.py` reads Claude Code's stream-json.
  New results with `AGENT=claude`:
  - T5: 0 findings either way. The skills add 37–43 tests vs 0–12, at about
    3–4× the cost.
  - T1: 12/12 either way. With the skills it takes 6–8 min vs 5.
- **Benchmark grader.** Summary lines ("Detected: Bloc … correct rulebook")
  and `confidence: high` are no longer counted as claims or severities.

### Changed

- **Benchmark.**
  - New task T5: a paginated, adaptive, accessible gallery.
  - New `new_*` counts: only the findings the agent added count.
  - A second re-run on v1.6.1. T1: the skills reach 12/12 recall in both
    runs, with more extra claims and about 3× the time. T2: the skills make
    0 claims contradicting bloclibrary, versus 1–2 without. T5 with the
    skills is inconclusive (see `bench/README.md`).

## [1.6.1] - 2026-10-18

### Fixed

- **CI failed on GitHub's runners since v1.0.0.** The scaffold tests compared
  generated file lists sorted with the runner's locale collation, which
  differs from byte order (`orders_repository_remote.dart` vs
  `orders_repository.dart`). The test now sorts with `LC_ALL=C`. The full
  suite also passes under `en_US.UTF-8`.

### Changed

- Every skill is versioned 1.6.1.

## [1.6.0] - 2026-10-18

The suite now has twenty-one skills and seventeen checkers.

### Added

- **flutter-firebase** treats Firebase as a data source behind the
  repository. It maps `FirebaseException` to failures and snapshots to
  entities, and keeps Firebase packages out of logic and views. It covers:
  - initialisation order, and options per flavor
  - Auth through `authStateChanges`
  - bounded Firestore queries and listeners tied to the logic holder
  - security rules that deny by default and are tested, plus App Check
  - FCM background handlers marked `@pragma('vm:entry-point')`
  - Remote Config with no secrets and no gates
  - emulators only in debug
  - fakes and the emulator suite in tests

  It ships `check_firebase.py` with 12 rules (`FIRE-001…012`). Three of them
  read `firestore.rules`, `storage.rules` and `database.rules.json`
  directly: open access, test-mode expiry, and auth-only writes.
- **dart-flutter-review** gets a `FIREBASE` section (whole project even in
  diff mode), `--no-firebase` / `--skip firebase`, reviewer Template R and
  dedupe rows.

### Fixed

- **Benchmark scoring.** `bench/grade.py` scored every checker as 0 findings
  when the ignored `suite_snapshot/` folder was missing. It now uses the
  repository's `skills/`, and stops with an error if a checker is missing.

### Fixed

- **Benchmark scoring.** `bench/grade.py` scored every checker as 0 findings
  when the ignored `suite_snapshot/` folder was missing. It now uses the
  repository's `skills/`, and stops with an error if a checker is missing.

### Changed

- `flutter-feature-scaffold` output is tested to produce zero FIRE findings.
- Every skill is versioned 1.6.0, and `install.sh` installs all twenty-one.
- **Benchmark re-run (2026-10-18), T3 and the new T4.** T3 reproduces the
  first result: baseline stores the token in `SharedPreferences` (SEC-001
  high), and skills uses `flutter_secure_storage` (0). T4 shows only a small
  difference on this model. See `bench/README.md`.

### Quality

- **Calibration.** `check_firebase.py` was calibrated on 215 projects, 47
  with Firebase: the canonical apps plus the FlutterFire examples, the
  Flutter team's Firebase codelabs, news_toolkit, io_flip and lichess. The
  canonical apps have no high or medium false positives.

  Its true positives include the FirebaseUI Auth codelab's test-mode rules,
  which expired in 2022.

## [1.5.0] - 2026-10-18

The suite now has twenty skills and sixteen checkers.

### Added

- **flutter-adaptive-layout** keeps one codebase working on phones, tablets,
  foldables, desktop and the web:
  - Material 3 window size classes defined once as shared tokens
  - `LayoutBuilder` vs `MediaQuery.sizeOf`
  - navigation bar, rail or drawer by size class
  - list-detail with selection that survives a resize, and foldable hinges
  - no app-wide orientation locks (Android 16+ ignores them on large
    screens)
  - hover, focus and keyboard shortcuts
  - `defaultTargetPlatform` and `.adaptive` widgets instead of `dart:io`
    `Platform` in UI
  - desktop minimum window sizes
  - tests across sizes with `tester.view`

  Layout is decided in views and components. Logic and state never know the
  screen size. It ships `check_adaptive.py` with 10 rules (`ADAPT-001…010`),
  including `dart:io Platform` reached on the web (a crash), app-wide
  orientation locks, layout chosen by device identity, screen size in logic
  and actions only reachable by hover.
- **dart-flutter-review** gets an `ADAPTIVE LAYOUT` section,
  `--no-adaptive` / `--skip adaptive`, reviewer Template Q and dedupe rows.
  ADAPT-001/002 replace `PLAT-platform-check-in-widget`.

### Changed

- `flutter-feature-scaffold` output is tested to produce zero ADAPT findings.
- Every skill is versioned 1.5.0, and `install.sh` installs all twenty.

### Quality

- **Calibration.** `check_adaptive.py` was calibrated on 163 projects:
  - the canonical apps, including the Flutter team's `material_3_demo` and
    `desktop_photo_search`
  - immich, lichess, hiddify, Wonderous, news_toolkit and io_flip

  The canonical apps have no high or medium false positives. Their one
  medium is a true positive.

## [1.4.1] - 2026-10-17

### Fixed

- **A static `Opacity` was reported nowhere.** When `check_performance.py`
  ran, `review.sh` deferred the `opacity-widget` candidate to PERFORMANCE.
  But PERF-005 reports only an `Opacity` that is animated or inside a list
  item, so a static one was dropped. The candidate now keeps its locations.
- **Stale examples.** `docs/examples/`, `sample-review.md` and the README's
  review preview were out of date. They predated the v1.1–v1.4 sections and
  the fixture's current line numbers, and they are now regenerated from the
  current scripts.

### Changed

- New cross-references between the skills:
  - error handling and persistence point to NET-004 for the HTTP client's
    retry policy
  - secure-defaults points to networking, platform integration and release
- Every skill is versioned 1.4.1.

## [1.4.0] - 2026-10-17

The suite now has nineteen skills and fifteen checkers.

### Added

- **flutter-platform-integration** covers native code as a data source:
  - **Placement.** Channels, Pigeon APIs and FFI bindings live in `data/`
    behind a repository or service. The repository maps `PlatformException`
    to a typed failure. Views and logic never touch a channel or a pointer.
  - **Channels:** MethodChannel, EventChannel and BasicMessageChannel, plus
    Pigeon.
  - **FFI:** memory ownership with `using()`, `free` and `NativeFinalizer`;
    ffigen and jnigen; native assets.
  - **Platform views** and their cost.
  - **Plugins:** federated layout with `PlatformInterface` and `verify`.
  - **Permissions:** asked at the moment of use, with permanent denial
    handled.
  - **Background isolates:** `BackgroundIsolateBinaryMessenger`.
  - **Testing:** mocked channels and fake platform interfaces.

  It ships `check_platform.py` with 12 rules (`PLAT-001…012`), among them
  channels outside the data layer, native memory never freed, libraries
  loaded from writable paths and channels in background isolates without the
  messenger. It skips generated Pigeon, ffigen and jnigen code.
- **dart-flutter-review** gets:
  - a `PLATFORM` section
  - `--no-platform` / `--skip platform`
  - reviewer Template P
  - dedupe rows (PLAT-003 beats `ERR-014` for channel calls, and PLAT-005
    beats the `undisposed-resource` candidate)

### Changed

- **Scaffold.** `flutter-feature-scaffold` output is tested to produce zero
  PLAT findings.
- **Versions.** Every skill is versioned 1.4.0, and `install.sh` installs all
  nineteen.

### Quality

- **Calibration.** `check_platform.py` was calibrated on the canonical apps
  and the Flutter team's platform samples (`platform_channels`, `add_to_app`
  with Pigeon, `pedometer` with FFI/jnigen, `platform_view_swift`), with no
  high or medium hits. It was also run on immich, lichess, hiddify (5 real
  native-memory leaks), news_toolkit, io_flip, Wonderous and 173 cached
  pub.dev plugins.

## [1.3.0] - 2026-10-17

The suite now has eighteen skills and fourteen checkers.

### Added

- **flutter-release** covers getting the app to the stores safely:
  - **Flavors and environments.** These are chosen once at the composition
    root and injected per architecture (a Riverpod override, get_it, a
    `RepositoryProvider` or a constructor).
  - **Signing.** Keystores and `key.properties` stay out of git, with Play
    App Signing for Android and CI secrets for iOS.
  - **Versioning.**
  - **Store requirements.** These are the application id, the target SDK and
    the iOS usage descriptions.
  - **CI/CD.** This covers GitHub Actions, Codemagic and Fastlane: no
    secrets in logs, no `pull_request_target` running untrusted code, and no
    keystore in artifacts.

  It ships `check_release.py` with 12 rules (`REL-001…012`). The checker
  reads Gradle, Xcode, plist and CI files as well as `lib/`. It is app-aware:
  sample apps get info at most for store-readiness rules.
- **dart-flutter-review** gets:
  - a `RELEASE` section that always covers the whole project, even in diff
    mode
  - the `--no-release` / `--skip release` flags
  - reviewer Template O
  - dedupe rows: REL-006 beats `AP-hardcoded-config-in-sources`, secrets stay
    `SEC-008/009`, and obfuscation stays `SEC-012`

### Changed

- Every skill is versioned 1.3.0, and `install.sh` installs all eighteen.

### Quality

- `check_release.py` was calibrated on the canonical apps, the Flutter
  team's `news_toolkit` example (real flavors), `io_flip`, immich, lichess,
  hiddify and Wonderous, and about 120 CI workflows. The canonical apps have
  no high or medium hits.

## [1.2.0] - 2026-10-17

The suite now has seventeen skills and thirteen checkers.

### Added

- **flutter-networking** covers the API client layer in each architecture:
  - **the client:** one configured Dio or `http` client provided through DI,
    with timeouts and interceptor order
  - **sources and repositories:** a remote source per resource, and DTO to
    entity mapping in the repository
  - **JSON:** validated at the DTO boundary
  - **requests:** pagination with an in-flight guard (Bloc transformers,
    notifier and Command guards), cancellation tied to the logic holder,
    retry for idempotent requests only, and WebSockets
  - **tests:** fake clients

  It ships `check_networking.py` with 10 rules (`NET-001…010`), among them
  clients without timeouts, a client per call, retries that re-send any
  method, unguarded page fetches and unclosed WebSockets. Transport security
  stays in `flutter-secure-defaults`.
- **dart-flutter-review:**
  - a `NETWORKING` section, `--no-net` / `--skip net`, and reviewer
    Template N
  - new dedupe rows: NET-004 beats `ERR-retry-non-idempotent`, NET-007 beats
    the `undisposed-resource` candidate, and NET-008 beats
    `AP-hardcoded-config-in-sources`
- **Benchmark:** task T4, a product list screen scored by the performance,
  design-system and accessibility checkers. `bench/all.sh` takes a `TASKS`
  list.

### Changed

- **Scaffold.** `flutter-feature-scaffold` output is now tested to produce
  zero findings from the performance, persistence, networking, design-system
  and accessibility checkers, in every profile and layout. The output was
  already clean; the tests now enforce it.
- **Versions.** Every skill is versioned 1.2.0, and `install.sh` installs all
  seventeen.

### Quality

- **Calibration.** `check_networking.py` was calibrated on the canonical
  apps plus hiddify, lichess, immich, Wonderous and the drift examples. The
  canonical apps have no high or medium false positives.

## [1.1.0] - 2026-10-17

Four new skills close the remaining coverage gaps. The suite now has sixteen
skills and twelve checkers.

### Added

- **flutter-performance** covers rebuild scope per architecture (Riverpod
  `select`, `BlocSelector`/`buildWhen`, `ListenableBuilder` with `child`,
  Provider `Selector`, narrow `Obx`), `const`, `RepaintBoundary`, lazy lists
  and slivers, isolates and `compute` in the data layer, image decode sizing,
  `saveLayer` costs and jank diagnosis with DevTools. It ships
  `check_performance.py` with 11 rules (`PERF-001…011`).
- **flutter-persistence** covers choosing between Drift, sqflite, Hive/Isar,
  shared_preferences and secure storage, cache policy, offline-first and
  sync, migrations, and where each piece sits in MVN, MVVM, Bloc and Clean.
  It is secure by default: parameterised SQL, encryption for sensitive
  stores, and a wipe on logout. It ships `check_persistence.py` with 9 rules
  (`PERSIST-001…009`), including SQL built from strings, schema bumps without
  a migration, Hive id collisions and databases opened per use.
- **flutter-design-system** covers tokens, Material 3 `ThemeData` and
  `ColorScheme`, `ThemeExtension` done right, a component layer, dark and
  high-contrast themes, and keeping visual tokens out of logic and state. It
  ships `check_design_system.py` with 12 rules (`DS-001…012`). The spacing and
  radius rules fire only when the app has a scale of its own.
- **flutter-accessibility** covers semantics and labels, tap targets, WCAG
  contrast (computed from the `ColorScheme`), text scale, focus and
  traversal, reduced motion, announcements placed per architecture, and
  screen-reader tests with `meetsGuideline`. Secrets are never put in
  semantics. It ships `check_accessibility.py` with 11 rules
  (`A11Y-001…011`).
- **dart-flutter-review** has four new sections and optional reviewer
  passes:
  - **Sections:** `PERFORMANCE`, `PERSISTENCE`, `DESIGN SYSTEM` and
    `ACCESSIBILITY`.
  - **Flags:** `--no-perf`, `--no-persist`, `--no-ds` and `--no-a11y`, plus
    the `--skip` keys `perf,persist,ds,a11y`.
  - **Reviewer passes:** Templates J–M.
  - **New dedupe rules:**
    - PERF beats `UI-eager-list`, `UI-opacity`, `UI-image-decode-size` and
      `UI-rebuild-scope`.
    - DS beats `UI-hardcoded-style`.
    - A11Y beats `UI-a11y`.
  - **Deferred heuristics:** when the matching checker ran, the
    `eager-children-map`, `opacity-widget` (until 1.4.1) and `hardcoded-color` candidates
    keep only their count.

### Changed

- Every skill is versioned 1.1.0.
- The hub's routing table and `flutter-ui-practices` point to the new
  specialists.
- `install.sh` installs all sixteen skills.
- `arch_check` no longer treats drift's "Generated by drift_dev when running
  build_runner" note in a hand-written `database.dart` as a generated-file
  banner.

### Quality

- **Calibration.** Each new checker was calibrated on the canonical apps
  (flutter/samples Compass, the felangel/bloc examples and the
  rrousselGit/riverpod examples) plus immich, lichess, Wonderous and the drift
  examples, all read-only. The canonical apps produce **no high or medium
  false positives**. Every false-positive cause that was fixed has a
  regression fixture.
- **Tests.** About 1,600 regression tests run without the Flutter SDK.

## [1.0.0] - 2026-10-16

First public release. These are twelve Agent Skills that help any coding agent write and review
Dart & Flutter code that is **clean and secure by default**, judged by the
app's own architecture.

### Skills

- **dart-flutter-best-practices** is the entry point and router. It provides
  WRITE mode, an Effective Dart checklist of 149 guidelines (each mapped to its
  lint or marked *judgment*), a recommended `analysis_options.yaml`, an
  `AGENTS.md` snippet and a format-on-write hook.
- **flutter-architecture** detects MVVM, MVN, Bloc/Cubit, MVC, GetX, Provider,
  Riverpod, setState and Clean Architecture, then judges the code by that
  pattern's own rules. It covers 28 automated rules (`arch_check.py`) and 28
  documented anti-patterns, and has a CI baseline mode.
- **flutter-feature-scaffold** generates a new feature in the project's own
  pattern (7 profiles, with or without Clean), copying the project's
  conventions. Output is secure by default and compile-tested, the tool
  dry-runs first and it never overwrites.
- **flutter-testing** gives a test strategy per architecture, documents test
  smells, and ships `test_gaps.py`, which ranks untested units by
  architectural priority.
- **flutter-error-handling** shows how errors flow through each architecture,
  compares `Result` with exceptions, covers global handlers, and ships
  `check_errors.py` with 14 rules.
- **flutter-secure-defaults** places write-time security per layer (tokens,
  storage, auth headers, logging, WebViews, cleartext, secrets) and ships
  `check_secure_defaults.py` with 12 rules. Deep audits are deferred to
  `flutter-security-audit`.
- **flutter-navigation** places navigation per architecture and covers
  go_router, deep-link validation and auth guards. It ships
  `check_navigation.py` with 12 rules.
- **flutter-forms** covers validation, form state per architecture, secure
  inputs and double-submit protection. It ships `check_forms.py` with 8 rules.
- **flutter-i18n** covers gen-l10n and ARB files, plurals, formatting, RTL and
  Arabic. It ships `check_i18n.py`, which checks catalog parity, Arabic plural
  forms, hardcoded strings, directional geometry and mojibake.
- **flutter-ui-practices** covers lifecycle and `dispose`, `BuildContext`
  after `await`, build cost, lists, keys, theming, accessibility and widget
  tests.
- **dart-naming** covers Effective Dart naming, Flutter conventions and role
  names per architecture.
- **dart-flutter-review** is the review orchestrator. It runs a mechanical
  pass with every checker, then parallel reviewer sub-agents. It verifies each
  High finding and produces one deduplicated report. It also ships a CI mode
  and a composite GitHub Action (`uses: abdelrahman-abied/flutter-pro-skills@v1`)
  that fails pull requests only on *new* violations.

### Quality

- Every checker is stdlib Python (3.8 or later) and read-only.
- The checkers are calibrated on real open-source apps before release:
  - flutter/samples Compass (MVVM)
  - the felangel/bloc examples
  - the rrousselGit/riverpod examples
  - lichess, hiddify, immich, Habo and others

  The canonical reference apps produce no high or medium false positives.
- About 900 regression tests run on macOS (bash 3.2) and Linux, without the
  Flutter SDK. A separate CI job compile-checks every scaffold profile with a
  real Flutter SDK.
- The skills follow the open [Agent Skills](https://agentskills.io) format and
  were verified with Claude Code and OpenCode.
