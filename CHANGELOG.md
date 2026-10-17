# Changelog

All notable changes to this project are documented here. The project follows
[Semantic Versioning](https://semver.org). Rule IDs (`ARCH-0xx`, `ERR-0xx`,
`SEC-0xx`, …) are part of the public contract: renaming or removing one is a
breaking change.

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
