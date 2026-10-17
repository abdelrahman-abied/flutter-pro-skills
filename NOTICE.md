# Notices and attribution

The skills in this repository are original work by Abdulrahman Obaid, released
under the MIT License (see `LICENSE`). Parts of them summarise, quote or adapt
third-party documentation, which remains under its own license. Changes were
made in every case: guidelines were condensed, reorganised into checklists,
mapped to analyzer rules, and annotated.

| Source | Used in | License |
|---|---|---|
| **Effective Dart**, https://dart.dev/effective-dart (dart-lang/site-www), © the Dart project authors | `skills/dart-flutter-best-practices/references/effective-dart.md` (guideline headings quoted verbatim), `skills/dart-naming/` | Content: [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). Code samples: BSD-3-Clause |
| **Dart linter rule registry**, dart-lang/site-www `src/data/linter_rules.json` | lint ↔ guideline mapping, `assets/analysis_options.yaml` | CC BY 4.0 / BSD-3-Clause |
| **Flutter documentation**: app architecture guide, case study, recommendations, design patterns, performance best practices, accessibility, theming and persistence cookbook. https://docs.flutter.dev (flutter/website), © the Flutter project authors | `skills/flutter-architecture/`, `skills/flutter-ui-practices/`, `skills/flutter-performance/`, `skills/flutter-persistence/`, `skills/flutter-design-system/`, `skills/flutter-accessibility/` | Content: [CC BY 3.0](https://creativecommons.org/licenses/by/3.0/) (as stated in the flutter/website LICENSE). Code samples: BSD |
| **Flutter style guide** (flutter/flutter `docs/contributing/Style-guide-for-Flutter-repo.md`) | `skills/dart-naming/`, `skills/flutter-ui-practices/` | BSD-3-Clause |
| **flutter_lints / lints** rule sets (flutter/packages, dart-lang/core) | `assets/analysis_options.yaml` | BSD-3-Clause |
| **Bloc documentation**: architecture, naming conventions, modeling state. https://bloclibrary.dev (felangel/bloc) | `skills/flutter-architecture/references/bloc.md`, `skills/dart-naming/` | MIT |
| **Riverpod documentation**: DO/DON'T. https://riverpod.dev (rrousselGit/riverpod) | `skills/flutter-architecture/references/state-management.md` | MIT |
| **MVN (Model-View-Notifier)** pattern, by Abdulrahman Abied: https://abdelrahman-abied.github.io/mvn-architecture-pattern | `skills/flutter-architecture/references/mvn.md`, `skills/dart-naming/` | Author's own work |
| **Agent Skills specification**: https://agentskills.io | skill format, `tests/validate_skills.py` (implements the published constraints; no text copied) | see agentskills.io |

Clean Architecture (Robert C. Martin), the Repository pattern (Martin Fowler,
*Patterns of Enterprise Application Architecture*) and MVC/MVVM are described
in our own words from widely published sources. No text is copied.

Trademarks (Dart, Flutter, and the names of coding agents) belong to their
owners. Mentioning an agent doesn't imply endorsement.
