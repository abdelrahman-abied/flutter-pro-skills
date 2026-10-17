# Suite contracts (maintainers & contributors)

This file is the single source of truth for everything that crosses a skill
boundary: file ownership, portability rules, rule IDs, output formats and CLIs.
If you change something here, update every skill that depends on it in the same PR.

Repo: `flutter-pro-skills`. Author: Abdulrahman Obaid (`abdelrahman-abied`). License: MIT
(content derived from dart.dev / docs.flutter.dev is CC BY; see `NOTICE.md`).

---

## 1. Layout and ownership

```
flutter-pro-skills/
├── README.md  LICENSE  NOTICE.md  AGENTS.md  install.sh  .gitignore
├── docs/CONTRACTS.md                     ← this file
├── tests/run_all.sh  tests/validate_skills.py
├── .github/workflows/test.yml
└── skills/
    ├── dart-flutter-best-practices/      hub: router + WRITE mode + Effective Dart + lints
    │   ├── SKILL.md
    │   ├── references/effective-dart.md   (generated from dart.dev; do not hand-edit rows)
    │   ├── assets/analysis_options.yaml   assets/AGENTS-snippet.md
    │   └── scripts/format-dart-hook.sh
    ├── dart-naming/                      naming conventions (Dart, Flutter, general, per-architecture roles)
    │   ├── SKILL.md  references/naming.md
    ├── flutter-ui-practices/             widgets, lifecycle, async/context, performance, theming, a11y, UI tests
    │   ├── SKILL.md  references/flutter-ui.md
    ├── flutter-architecture/             architecture detection, patterns, anti-patterns, import-graph checker
    │   ├── SKILL.md
    │   ├── references/  detect.md mvvm.md mvn.md mvc.md clean-architecture.md
    │   │                repository-pattern.md bloc.md state-management.md anti-patterns.md (index)
    │   │                anti-patterns/<group>.md (entries, see §15)
    │   ├── scripts/arch_check.py
    │   └── tests/  run.sh  fixtures/…  (expected results asserted in run.sh)
    └── dart-flutter-review/              review orchestrator (mechanical pass + parallel reviewers + report)
        ├── SKILL.md  references/review-guide.md  references/finding-format.md
        ├── scripts/review.sh  scripts/heuristics.py
        └── tests/run.sh  tests/fixtures/…
```

| Owner (build phase) | Files |
|---|---|
| Lead | root files, `docs/`, `tests/`, `.github/` |
| Agent A: architecture knowledge | `skills/flutter-architecture/SKILL.md`, `skills/flutter-architecture/references/**` |
| Agent B: architecture tooling | `skills/flutter-architecture/scripts/**`, `skills/flutter-architecture/tests/**` |
| Agent C: split skills | `skills/dart-naming/**`, `skills/flutter-ui-practices/**` |
| Agent D: hub + review | `skills/dart-flutter-best-practices/**`, `skills/dart-flutter-review/**` |

Never edit a file you don't own. If you need a change in someone else's file,
say so in your final report.

---

## 2. Portability rules (any agent, not just one vendor)

The skills follow the open Agent Skills standard (https://agentskills.io/specification)
and must work in Claude Code, Cursor, Codex, Gemini CLI, GitHub Copilot, OpenCode,
Antigravity, and plain "read this file" agents.

**Frontmatter** (validated by `tests/validate_skills.py`):

```yaml
---
name: <must equal folder name; a-z 0-9 single hyphens; ≤64>
description: <≤1024 chars, target ≤900; what it does + when to use; keyword-rich; "pushy">
license: MIT
metadata:
  author: abdelrahman-abied
  version: "1.0.0"
  suite: flutter-pro-skills
---
```

There is no `allowed-tools` field (it's experimental and vendor-specific), and
there is no `compatibility` field unless a skill really needs one.

**Body:**
- SKILL.md must be ≤500 lines, and ideally ≤~5000 tokens. References sit one
  level deep. Any reference over 300 lines starts with a `## Contents` list.
- **No vendor tool names.** Don't write "Skill tool", "Agent tool",
  "Task tool", "Read/Edit/Write tool", "ToolSearch" or "PostToolUse" as
  instructions. Say "read", "run", "spawn a sub-agent if your agent supports
  it". You may mention a vendor *as an example* (e.g. "Claude Code's
  Agent/Task tool, Codex sub-agents"), but always provide the fallback.
- The project instructions file is "your agent's project instructions file
  (`AGENTS.md`, `CLAUDE.md`, `GEMINI.md`, `.cursor/rules/…`, `.github/copilot-instructions.md`)".
  Don't say only `CLAUDE.md`.
- **Cross-skill references** use the skill name plus a relative path fallback.
  For example: "load the `flutter-architecture` skill (if your agent doesn't
  auto-load skills, read `../flutter-architecture/SKILL.md`)". Assume the
  suite is installed as sibling folders. If a sibling is missing, degrade
  gracefully and say so.
- Paths inside a skill are relative to the skill root (`scripts/review.sh`,
  `references/naming.md`). `<skill-dir>` means "the folder containing this SKILL.md".

**Scripts:**
- Use `bash` (must run on macOS bash 3.2 and Linux bash 5, with no GNU-only
  flags) and `python3` (≥3.8, **stdlib only**).
- Scripts are **read-only**: they never modify the analysed project.
- Always run Python with `python3 -I` (isolated mode) when a script invokes it.
- Exit codes: `0` means the report was produced (findings don't fail the run),
  `2` means a usage or environment error. A future `--ci` flag may exit `1` on
  High findings.

**Writing style:** explain *why*, use the imperative, avoid all-caps MUSTs,
match the voice of the existing references. Keep each rule at the strength of
its source: **DO/DON'T** ≈ always, **PREFER/AVOID** = unless there's a good
reason, **CONSIDER** = depends on context.

---

## 3. Shared vocabulary

**Precedence when sources disagree** (all skills):
1. The project's own decisions: its lint config, its project instructions
   file, its declared architecture, and conventions used consistently in the
   code.
2. The pattern's own canonical source (MVN → the `mvn` spec by its author;
   Bloc → bloclibrary.dev; Riverpod → riverpod.dev; MVVM → docs.flutter.dev
   architecture guide).
3. Effective Dart.
4. Flutter team guidance for apps.
5. The Flutter framework's internal style guide. Use it only where the project
   already follows it.

**Severity** (findings):

| Severity | Meaning |
|---|---|
| High | A bug now or under ordinary use: crash, leak, lost error, wrong UI, or an architecture violation that defeats the pattern's core guarantee (e.g. I/O inside widgets, domain depending on data) |
| Medium | Noticeably hurts maintainability, testability or performance, or is a costly API to change later |
| Low | Idiom or consistency issue with an easy, local fix |
| Info | Observations and trade-offs, not defects (e.g. "pass-through use cases add ceremony") |
| Mechanical | Fully resolved by `dart fix --apply` / `dart format`. Always reported as **one** collapsed finding |

---

## 4. Finding format (every reviewer pass returns this)

Reviewer passes (the parallel sub-agents in `dart-flutter-review`) return their
findings as Markdown text in exactly this shape, so the lead can merge and
dedupe them mechanically:

```markdown
### [HIGH] AnimationController never disposed
- id: UI-lifecycle            # ARCH-0xx | AP-xxx | NAME-xxx | UI-xxx | ED-xxx | LINT:<code>  (slugs are lowercase)
- where: lib/ui/home/home_screen.dart:31, lib/ui/cart/cart_screen.dart:12
- evidence: `late final _c = AnimationController(vsync: this);` with no dispose() override
- rule: Flutter: dispose what you create (flutter-ui-practices › flutter-ui.md §1)
- why: keeps ticking and retains the State after pop → memory/CPU leak per visit
- fix: |
    @override
    void dispose() { _c.dispose(); super.dispose(); }
- confidence: confirmed       # confirmed (read the code) | likely (strong signal, not fully traced)
```

ID prefixes:
- `ARCH-0xx`: import-graph rules (§6)
- `ARCH-1xx`: code-pattern rules (§6)
- `AP-<slug>`: documented anti-patterns with no automated check (in anti-patterns.md)
- `NAME-<slug>`: naming
- `UI-<slug>`: Flutter UI and lifecycle
- `ED-<slug>`: an Effective Dart guideline
- `LINT:<code>`: an analyzer diagnostic
- `SEC-<slug>`: a security finding (optional pass that defers to the separate `flutter-security-audit` skill)

Use free-form but stable slugs for NAME/UI/ED (e.g. `NAME-get-prefix`,
`UI-context-after-await`, `ED-future-void`).

---

## 5. Architecture profile (output of `arch_check.py --json`)

```json
{
  "schema": "flutter-pro-skills/arch-profile@1",
  "root": "/abs/path", "package": "my_app",
  "profile": {
    "presentation": "mvn|mvvm|bloc|mvc|getx|provider|riverpod|setstate|unknown",
    "clean_architecture": true,
    "repository_pattern": true,
    "use_cases": true,
    "layout": "feature-first|layer-first|hybrid",
    "state_management": ["riverpod"],
    "di": ["riverpod", "get_it"],
    "confidence": "high|medium|low",
    "signals": ["dependency: flutter_riverpod, riverpod_annotation", "12 files under features/*/presentation/notifier/", "suffix *Notifier x14"]
  },
  "stats": {"files": 120, "by_layer": {"domain": 30, "data": 35, "presentation": 45, "core": 8, "app": 2}, "features": ["auth", "movie"]},
  "violations": [
    {"id": "ARCH-005", "name": "ui-depends-on-data-source", "severity": "high",
     "file": "lib/features/movie/presentation/view/movie_view.dart", "line": 4,
     "evidence": "import 'package:dio/dio.dart';",
     "message": "A view imports a transport/data-source; route it through the notifier/view model.",
     "note": ""}
  ],
  "suppressed": [{"id": "ARCH-001", "file": "lib/features/movie/domain/usecases/movie_usecase.dart", "line": 7, "reason": "MVN DI seam (use-case provider)"}]
}
```

### Detection of `presentation` (most specific wins; the evidence goes in `signals`)

| Value | Strong signals |
|---|---|
| `mvn` | Riverpod dependency **and** (`notifier/` folders under `presentation/`, **or** ≥3 `*Notifier` classes extending a generated `_$X`), **and** no `view_model(s)/` folders |
| `mvvm` | `view_model(s)/` or `viewmodel(s)/` folders, or ≥3 `*ViewModel` classes (with any state solution: ChangeNotifier, Provider, Riverpod, stacked) |
| `bloc` | `bloc` / `flutter_bloc` dependency, or `*_bloc.dart` / `*_cubit.dart` files |
| `getx` | `get` dependency and `GetxController` subclasses |
| `mvc` | `mvc_pattern` / `fluttery_framework` dependency, or `controller(s)/` folders with `*Controller` classes that aren't GetX and aren't Flutter's own controllers, plus `model(s)/` + `view(s)/` |
| `provider` | `provider` dependency, ChangeNotifier models, and no view-model naming |
| `riverpod` | Riverpod dependency without MVN folder or naming conventions |
| `setstate` | No state-management dependency, mostly StatefulWidget plus setState |
| `unknown` | Nothing conclusive |

`clean_architecture`: there are `domain/` and `data/` directories (top-level
or per feature), plus at least one of `usecases/`|`use_cases/` or `entities/`.
`repository_pattern`: there are `*Repository` types.
`layout`: `feature-first` if `lib/features/` (or `lib/modules/`, `lib/feature/`)
holds ≥1 feature (see "As built"), `layer-first` if top-level `lib/{data,domain,presentation,ui,screens,models,services}`,
and `hybrid` if both.
The CLI's `--profile <value>` overrides the presentation detection (a
declared architecture beats inference).

### File classification (layers and roles)

Path segments are matched case-insensitively. **Skip** generated files
(`*.g.dart`, `*.freezed.dart`, `*.gr.dart`, `*.mocks.dart`, `*.config.dart`,
`lib/generated/`, `l10n` output).

- **Layer**, from the first match among these path segments:
  - `domain`
  - `data`
  - `presentation`, `ui`, `view(s)`, `screens`, `pages`, `widgets`
  - `core`, `shared`, `common`, `utils`
  - `app`, `di`, `injection`, `router`, `routes`, or `lib/main*.dart`. This is the composition root, which may import anything.
  - In layer-first projects: `models`, `services`, `repositories`, `api`, `datasources` count as **data**.
- **Role**, from folder or suffix:
  - `entity`
  - `repository-contract` (domain/repositories, or an `abstract`/`interface` repository class)
  - `repository-impl` (data/repositories, or `*_repository_impl.dart`)
  - `usecase`
  - `dto` (data/models, `*_dto.dart`, `*_request.dart`, `*_response.dart`)
  - `source` (sources/, datasources/, data_sources/, api/, remote/, local/, `*_source.dart`, `*_api.dart`, `*_client.dart`)
  - `service` (services/, `*_service.dart`)
  - `logic` (notifier(s)/, view_model(s)/, viewmodel(s)/, bloc(s)/, cubit(s)/, controller(s)/, plus suffixes `_notifier`, `_view_model`, `_viewmodel`, `_bloc`, `_cubit`, `_controller`, `_store`)
  - `state` (state/, `*_state.dart`)
  - `view` (view(s)/, screens/, pages/, `*_screen.dart`, `*_page.dart`, `*_view.dart`)
  - `widget` (widget(s)/, other presentation files)
  - `other`
- **Feature**: the path segment after `features/`, `feature/` or `modules/`.
- **I/O packages** (transport/persistence): `dio`, `http`, `retrofit`,
  `chopper`, `graphql`, `graphql_flutter`, `sqflite`, `drift`, `hive`,
  `hive_flutter`, `isar`, `objectbox`, `shared_preferences`,
  `flutter_secure_storage`, `cloud_firestore`, `firebase_database`,
  `firebase_storage`, `firebase_auth`, `supabase_flutter`, `supabase`,
  `web_socket_channel`, `grpc`, `path_provider`.

Imports are resolved for relative paths and for `package:<own package>/…`
(from pubspec `name:`). External packages are recorded by package name.
`export` directives are treated like imports.

---

## 6. Architecture rule catalog

Agent A documents **every** rule below in `anti-patterns.md`: the problem, why it
matters, a bad/good Dart example, the fix, and its profile notes. Agent B
implements every rule whose detection is `import` or `regex`, using exactly
these IDs, names and default severities. "Profiles" says where a rule applies.
`all` means every presentation profile, including unknown.

### Import-graph rules

| ID | name | default severity | profiles | rule |
|---|---|---|---|---|
| ARCH-001 | domain-depends-on-data | high | where a domain layer exists | A domain file imports a data-layer file. **MVN suppression:** a file under `domain/usecases/` containing `@riverpod`, importing a `repository-impl` file, goes to `suppressed` with the reason "MVN DI seam (use-case provider)" |
| ARCH-002 | domain-depends-on-presentation | high | where a domain layer exists | A domain file imports a presentation file |
| ARCH-003 | domain-depends-on-framework | medium | where a domain layer exists | A domain file imports `package:flutter/*` (except `foundation.dart`, which is **low**), any I/O package, `flutter_riverpod`/`hooks_riverpod`, `flutter_bloc`, `provider` or `get`. `riverpod_annotation`/`riverpod` are allowed in `domain/usecases/` under the mvn profile |
| ARCH-004 | data-depends-on-presentation | high | all | A data file imports a presentation file |
| ARCH-005 | ui-depends-on-data-source | high | all | A `view`/`widget` role file imports a `source`/`service`/`repository-impl` file or an I/O package |
| ARCH-006 | ui-depends-on-dto | medium | clean_architecture=true, or the imported file is `*_dto/_request/_response.dart` | A presentation file imports a `dto` file |
| ARCH-007 | logic-depends-on-concrete-data | medium | all | A `logic` file imports a `source`/`service`/`repository-impl` file or an I/O package. (Importing an abstract repository contract is fine) |
| ARCH-008 | view-depends-on-repository | medium | mvvm, mvn, bloc, mvc, getx | A `view`/`widget` file imports a repository (contract or impl) or a use case. **Bloc exemption:** the file contains `BlocProvider(`, `RepositoryProvider(` or `MultiRepositoryProvider(` |
| ARCH-009 | logic-depends-on-flutter-ui | medium | all (getx: low) | A `logic` file imports `package:flutter/material.dart`, `widgets.dart` or `cupertino.dart` (`foundation.dart` is OK) |
| ARCH-010 | sibling-logic-dependency | medium | bloc (medium), mvvm/mvc/getx (low); **not** mvn/riverpod (the MVN spec sanctions `ref.watch(otherProvider)` in `build()`) | A `logic` file imports another `logic` file (excluding its own state/event `part`s) |
| ARCH-011 | repository-depends-on-repository | medium | all | A repository file imports another repository file. **Exempt:** an impl importing its own contract (same stem with `_impl` removed) |
| ARCH-012 | mvn-notifier-bypasses-usecase | medium | mvn only | A notifier imports a `repository-contract`, `repository-impl`, `source` or `service` file instead of a use case |
| ARCH-013 | core-depends-on-feature | medium | feature-first, hybrid | A `core`/`shared`/`common` file imports a file under `features/` |
| ARCH-014 | cross-feature-internal-import | low | feature-first, hybrid | `features/a/**` imports `features/b/(data|presentation)/**`. Importing `features/b/domain/**` is allowed |
| ARCH-015 | feature-cycle | medium | feature-first, hybrid | There is a cycle in the feature→feature import graph. Report once per cycle, with the path `a → b → a` |

### Code-pattern rules (regex/heuristic, per file; comments stripped)

| ID | name | default severity | profiles | rule |
|---|---|---|---|---|
| ARCH-101 | io-in-widget | high | all | A widget/State file (`extends StatelessWidget|StatefulWidget|ConsumerWidget|ConsumerStatefulWidget|HookWidget|HookConsumerWidget` or `extends State<`) contains `http.(get|post|put|patch|delete)(`, `Dio(`, `dio.(get|post|put|patch|delete|request)(`, `SharedPreferences.getInstance(`, `FirebaseFirestore.instance`, `openDatabase(` or `jsonDecode(` |
| ARCH-102 | context-in-logic | medium | all (not getx for `Get.` navigation) | A `logic` file has a `BuildContext` parameter or field, or calls `Navigator.of(`, `ScaffoldMessenger.of(`, `showDialog(`, `showModalBottomSheet(`, `context.go(`/`context.push(` |
| ARCH-103 | god-file | medium | all | A non-generated file whose length exceeds its role's limit. The default limits are logic >400 lines, view/widget >500, and any file >800. Report the line count |
| ARCH-104 | service-locator-in-ui | low | all except getx | A `view`/`widget` file uses `GetIt.I`, `GetIt.instance`, `getIt<`, `getIt(`, `sl<`, `locator<` or `Get.find<` |
| ARCH-105 | global-mutable-state | medium | all | A top-level variable that isn't `final`/`const` in `lib/`, or a `static` field that isn't `final`/`const` in a class that isn't a Flutter `State` |
| ARCH-106 | mutable-state-class | medium | mvn, bloc, riverpod, mvvm | A `state`-role file (not a Flutter `State<…>` subclass) declares an instance field that isn't `final` |
| ARCH-107 | repository-leaks-transport | medium | repository_pattern=true | A repository file has a public method returning `Response<`, `http.Response`, `Map<String, dynamic>`, or a type ending in `Dto`/`Response`/`Request` |
| ARCH-108 | concrete-repository-only | low | clean_architecture=true, mvn, mvvm | A `class XRepository` is concrete and no `abstract`/`interface`/`sealed` `XRepository` exists anywhere in `lib/` |
| ARCH-109 | ephemeral-state-in-provider | low | riverpod, mvn, provider | A `logic` file, or a file declaring providers (`@riverpod`, `Provider(`, `NotifierProvider`, `ChangeNotifierProvider(`), constructs a `TextEditingController`, `ScrollController`, `FocusNode`, `PageController` or `TabController` |
| ARCH-110 | provider-init-from-widget | low | riverpod, mvn | An `initState()` body contains `ref.read(` followed by a call on the result (e.g. `ref.read(p.notifier).load()` or `ref.read(p).init()`) |
| ARCH-111 | event-flag-in-state | low | mvn, bloc, mvvm, riverpod | A `state`-role file declares a `bool` field named `show*`, `should*`, `navigate*`, `open*`, `pop*` or `is*Shown`, i.e. a one-time event modelled as persistent state |
| ARCH-112 | mvn-forbidden-naming | low | mvn only | Class declarations ending in `ViewModel`, `VM` or `Controller` (except Flutter/animation controllers declared as fields), or `controller(s)/`/`view_model(s)/` folders |
| ARCH-113 | getx-in-build | low | getx | `Get.put(` or `Get.find(` inside a `build(` method of a widget file |

### Documented-only anti-patterns (agent judgment; Agent A defines them, no script)

These use `AP-` slugs. The minimum set:

- `AP-massive-view`: logic in widgets, or a "smart UI"
- `AP-god-viewmodel`: also god notifier / god bloc
- `AP-boolean-soup-state`: `isLoading` + `error` + `data` that can contradict each other
- `AP-null-as-loading`
- `AP-dto-as-ui-state`
- `AP-leaky-repository`: exposes transport errors and types
- `AP-two-sources-of-truth`
- `AP-passthrough-usecase`: Info, and not flagged under mvn, where it is prescribed
- `AP-premature-domain-layer`: over-architecting a small app
- `AP-interface-for-everything`: when there is no second implementation or fake
- `AP-exceptions-across-layers`: vs. a Result type (Flutter design-patterns/result)
- `AP-stream-subscription-in-widget`
- `AP-bloc-to-bloc`: the reading-level counterpart of ARCH-010
- `AP-singleton-abuse`
- `AP-context-passed-down-to-data`
- `AP-hardcoded-config-in-sources`
- `AP-navigation-in-logic`: and the sanctioned ways per pattern
- `AP-shared-mutable-model`
- `AP-feature-envy-across-features`
- `AP-anemic-vs-fat-entity`: and when anemic entities are *fine* in Flutter
- `AP-mvc-massive-controller`
- `AP-getx-service-locator-everywhere`
- `AP-riverpod-dynamic-providers`
- `AP-riverpod-side-effects-in-provider-build`

Added during the build (documented in anti-patterns.md):

- `AP-viewmodel-exposes-repository` (low)
- `AP-mvn-legacy-riverpod-syntax` (low, mvn only)
- `AP-default-hides-missing-state` (low)
- `AP-mixed-architecture` (medium, or info for a documented migration). Report it **once** per codebase, never per file.

### As built (deviations recorded after the build; these win over the text above)

- **Layer order:** domain → data → presentation → composition root → core. So
  `lib/core/data/x` is data and `lib/core/router/` is the composition root.
  ARCH-013 uses a separate "core area" test: under core/shared/common, outside
  `features/`, and not the composition root.
- **Composition root:** `lib/main*.dart`, files directly in `lib/app/`, and
  `di/ injection/ router/ routes/ routing/` folders. `lib/app/<subfolder>/**`
  is classified by its role folder (get_cli layouts).
- **Features:** detected wherever `features/`, `feature/` or `modules/` appears.
  **One** feature is enough for `feature-first` (`hybrid` if layer-first
  top-level folders also exist).
- **Fallbacks:**
  - A file with no layer segment takes its layer from its role.
  - `models/services/repositories/api/datasources` mean data in any layout.
  - Role gating: no UI roles in domain or data, no data roles in domain or
    presentation.
  - An abstract `*Repository` under `data/repositories/` is a
    repository-contract.
  - Content decides the role last: `@riverpod class`, `extends _$`,
    Cubit/Bloc/GetxController mean logic; Widget subclasses mean widget.
- **New role `event`** (`*_event(s).dart`), so Bloc events aren't `logic`.
- **Symbol usage** (ARCH-005/007/008/011/012, file targets): an import counts
  only if the importer references a *primary* symbol of the target: a
  contract, a `*Repository`/`*Source`/`*Service`/`*UseCase` class, a class
  with async methods or `call()`, an implementor of one of those, or a
  provider. Enums, exceptions, value classes and pure functions don't count.
  I/O package imports always count. For ARCH-011 the symbol must be a
  `*Repository` or a provider. The own-contract exemption also covers stem
  prefixes (`auth_repository_remote` → `auth_repository`).
- **Rule refinements:**
  - ARCH-111 matches only event-like names (see anti-patterns.md).
  - ARCH-101 counts hits only inside widget classes, and ARCH-109 only
    outside them.
  - ARCH-102 also matches `Navigator.push*/pop*`.
  - ARCH-104 also matches `getIt.get<` and `sl()`.
  - ARCH-113 also matches `Get.lazyPut` and `Get.find<T>`.
  - ARCH-105 exempts `@visibleForTesting`.
  - ARCH-112 exempts real `*Controller` supertypes, and reports a forbidden
    folder once.
  - ARCH-003 flags riverpod in domain except under mvn in `domain/usecases/`.
  - ARCH-010 is low under provider, setstate and unknown.
  - ARCH-015 reports at most 50 cycles of up to 8 features.
- **Detection order:** mvn, getx, mvvm, bloc, mvc, provider, riverpod,
  setstate. A `get` dependency alone means getx with low confidence. Under an
  explicit non-mvn `--profile`, MVN allowances stop applying.
- **Also skipped as generated:** `app_localizations*`, `messages_*`, the
  `l10n.yaml` `output-dir`, `*.pb*.dart`, `*.chopper.dart`, and any file whose
  header says "GENERATED CODE - DO NOT MODIFY".
- **No `lib/`:** an empty report with exit 0.

### Suppression

Projects can silence a rule with comments, which `arch_check.py` honours:

- `// arch-ignore: ARCH-005 <reason>` on the offending line or the line above it
- `// arch-ignore-file: ARCH-005 <reason>` anywhere in the file

Suppressed hits go to `suppressed` with the reason.

---

## 7. CLIs

`skills/flutter-architecture/scripts/arch_check.py`:

```
python3 -I arch_check.py <project-root> [--json] [--files <file-with-relative-paths>]
                         [--profile auto|mvn|mvvm|bloc|mvc|getx|provider|riverpod|setstate]
                         [--max <n>]   # example locations per rule in text mode (default 5)
```

- The script builds the full graph over `lib/`. `--files` limits **reported
  violations** to those files (for diff reviews).
- Text output has two sections. `== ARCHITECTURE PROFILE` holds key: value
  lines, and `== ARCHITECTURE VIOLATIONS` holds groups
  `  [ARCH-005] ui-depends-on-data-source (high) x3 — <message>` followed by
  `      <file>:<line>  <evidence>` lines and `      ... N more`. Suppressed
  hits come last as `  suppressed: N (see --json)`.
- Exit codes: 0 means report produced, 2 means usage error (e.g. no `pubspec.yaml`).

`skills/dart-flutter-review/scripts/review.sh` (existing, extended by Agent D):

```
bash review.sh <project-root> [--diff <git-ref>] [--no-extra] [--no-arch] [--profile <p>] [--max n]
```

- It calls `../flutter-architecture/scripts/arch_check.py` when present (and
  prints `== ARCHITECTURE (skipped: flutter-architecture skill not installed)`
  otherwise), passing `--files` in diff mode.
- It finds the stricter lint set at
  `../dart-flutter-best-practices/assets/analysis_options.yaml`, and skips the
  EXTRA LINTS section if that file is missing.

---

## 8. Tests

- `tests/run_all.sh` runs `tests/validate_skills.py` and then every
  `skills/*/tests/run.sh`. It exits non-zero on any failure.
- A skill's `tests/run.sh` must:
  - work without the Flutter SDK, skipping (not failing) the parts that need
    `dart`
  - print `PASS`/`FAIL` lines
  - exit 1 on failure
- Fixtures are tiny projects: a `pubspec.yaml` with `name:` and the
  dependencies the profile needs, plus `lib/**`. **No `pub get` needed.**
  arch_check is static.
- CI: `.github/workflows/test.yml` runs `tests/run_all.sh` on ubuntu-latest
  and macos-latest.

---

# Phase 2 contracts (v1.1)

## 9. New skills and ownership

| Owner | Files |
|---|---|
| Lead | `README.md`, `docs/CONTRACTS.md`, `install.sh`, `tests/`, `skills/dart-flutter-best-practices/SKILL.md` (routing table only), the final integration |
| Agent E | `skills/flutter-testing/**` (new skill) |
| Agent F | `skills/flutter-error-handling/**` (new skill) |
| Agent G | `skills/flutter-feature-scaffold/**` (new skill) |
| Agent H | `skills/flutter-architecture/scripts/**`, `skills/flutter-architecture/tests/**`, `skills/dart-flutter-review/**`, root `action.yml` |
| Agent I | `docs/assets/**`, `docs/examples/**`, `docs/PUBLISHING.md`, `CONTRIBUTING.md`, `.github/ISSUE_TEMPLATE/**`, `.github/pull_request_template.md`, `.github/CODEOWNERS` |

The rules in §2 (portability, frontmatter, ≤1024-char descriptions,
python3 stdlib, bash 3.2, read-only analysis scripts) apply to every new
skill. Each new skill ships a `tests/run.sh` (§8), which `tests/run_all.sh`
picks up automatically. Use `metadata.suite: flutter-pro-skills` and
`version: "1.1.0"`.

New finding-ID prefixes (§4):
- `TEST-<slug>`: testing.
- `ERR-0xx` for rules found by a script, `ERR-<slug>` for findings from
  reading the code: error handling.
- Scaffold doesn't report findings.

## 10. Per-file classification in the arch profile (Agent H adds; E, F and G consume)

`arch_check.py --json` gains a top-level `"files"` array. The schema string
stays `arch-profile@1`, because the change only adds keys:

```json
"files": [{"file": "lib/features/cart/presentation/notifier/cart_notifier.dart",
           "layer": "presentation", "role": "logic", "feature": "cart",
           "classes": ["CartNotifier"]}]
```

`classes` lists the top-level class, mixin and enum names declared in the
file. Consumers find the checker at `../flutter-architecture/scripts/arch_check.py`
(relative to their own skill root). If it is missing, they fall back to their
own minimal classification and say so in their output. They must not import
its Python internals; they only run it as a subprocess and read the JSON.

## 11. CLIs

`flutter-testing/scripts/test_gaps.py` (E). Read-only.
```
python3 -I test_gaps.py <project-root> [--json] [--profile <p>] [--max n]
```
- Maps each `lib/` unit (by role: repository-impl, usecase, logic, source,
  service, view, widget) to its test files. The test file is found by mirrored
  path (`test/<same path>_test.dart`), else by a name match, else by a test
  importing the unit.
- Reports **untested units, ranked by architecture priority**. The order is
  repositories and use cases, then logic (notifier, view model, bloc), then
  sources and services, then views.
- Also reports test smells found by regex over `test/**`:
  - tests with no `expect`/`verify`
  - `sleep`/`Future.delayed` in tests
  - real `http.Client()`/`Dio()` in unit tests
  - `skip:` without a reason
  - one test file over 800 lines
  - mocks of the class under test
- Text output follows the arch_check style: `== TEST GAPS` and
  `== TEST SMELLS`, then groups `[TEST-<slug>] (sev) xN — message` with
  example locations.

`flutter-error-handling/scripts/check_errors.py` (F). Read-only.
```
python3 -I check_errors.py <project-root> [--json] [--files <list>] [--profile <p>] [--max n]
```
- Rules `ERR-001…` are defined by F and documented in its `references/`.
  The minimum set:
  - a swallowed catch
  - a catch with no `on` in a data or domain layer that doesn't rethrow or map
  - catching `Error`
  - a repository letting transport exceptions escape (`DioException`,
    `SocketException`, `http.ClientException`, `FormatException`) with no
    mapping
  - `throw` of a String or Map
  - a domain or use-case layer that throws transport types
  - `Future` APIs in repositories that return `null` on failure
  - presentation showing `e.toString()` to the user
  - mixing `Result` and throwing within one repository
- Output style is the same as test_gaps.

`flutter-feature-scaffold/scripts/scaffold.py` (G). This is the **only
script in the suite that writes files**, and only with `--write`.
```
python3 -I scaffold.py <project-root> <feature_name> [--profile auto|mvn|mvvm|bloc|cubit|getx|provider|riverpod]
                       [--clean] [--entity <Name>] [--write] [--force-dir]
```
- The default is a **dry run** that prints the files it would create and their
  contents' outline.
- `--write` creates the files, and **never overwrites** an existing file: it
  skips it and reports the skip.
- `auto` reads the profile with `arch_check --json` and copies the project's
  existing conventions: feature-first vs layer-first, singular vs plural
  folders (`notifier/` vs `notifiers/`), `Screen`/`Page`/`View`, and
  `Impl`/`Remote` naming. If it can't infer them, it uses the pattern's
  canonical layout from `flutter-architecture/references/<pattern>.md`.
- Generated code must pass `dart analyze` with the project's dependencies (for
  example, MVN output needs `riverpod_annotation` and build_runner). The
  script prints the dependencies and the codegen command it needs. It doesn't
  run them.

CI mode (H), in `arch_check.py`:
```
--baseline <file>        report only violations not in the baseline
--write-baseline <file>  write the current violations as a baseline, then exit 0
--ci [--fail-on high|medium|low]   exit 1 if any reported violation is at or above fail-on (default high)
```
- The baseline file is JSON: `{"schema":"flutter-pro-skills/arch-baseline@1","entries":[{"id","file","key"}]}`.
- `key` is a normalised evidence string with no line numbers, so harmless
  edits don't invalidate the baseline. Entries are counted per (id, file, key),
  so duplicates are tracked.
- `review.sh` gains `--ci`, `--fail-on <sev>` and `--baseline <file>`. In CI
  mode it exits 1 when the architecture violations at or above fail-on are new
  versus the baseline, or when the analyzer reports errors. The run also
  writes a Markdown summary to `$GITHUB_STEP_SUMMARY` when that variable is
  set.
- The root `action.yml` is a composite GitHub Action. Its inputs are:
  - `path` (default `.`)
  - `base-ref` (diff mode)
  - `fail-on` (default `high`)
  - `baseline` (optional)
  - `flutter` (default `false`; when `true`, it installs Flutter via
    subosito/flutter-action and runs the full review.sh, otherwise only
    arch_check)

  It must work as `uses: abdelrahman-abied/flutter-pro-skills@v1`.

## 12. Review integration (H)

`dart-flutter-review` adds optional reviewer passes:
- **testing**, which loads `flutter-testing` and runs `test_gaps.py`
- **errors**, which loads `flutter-error-handling` and runs `check_errors.py`

`review.sh` prints `== TEST GAPS` and `== ERROR HANDLING` sections when the
sibling scripts exist (`--no-tests` and `--no-errors` skip them), and it skips
gracefully when they're missing.

Agents E and F must keep their CLIs exactly as specified in §11, because H
builds against them in parallel.

## 13. Phase 2 as built (these entries win over §9–12)

- **arch_check.py CI flags:**
  - `--baseline <file>`, `--write-baseline <file>`, and `--ci [--fail-on high|medium|low]`.
  - Text mode adds two lines: `summary: N new, M baselined` (plus how many
    baseline entries no longer match) and `ci: pass|fail (N at or above <sev>)`.
  - JSON adds `baseline` and `ci` objects.
  - A bad or missing baseline exits 2.
  - With `--ci`, the script exits 1 on failure, so §2's "future `--ci`" is now
    real.
  - Keys normalise whitespace. ARCH-103's key is "N lines", so a growing file
    still matches its baseline entry.
- **review.sh flags:** `--ci`, `--fail-on`, `--baseline`, `--no-tests`,
  `--no-errors`. It adds three sections: `== TEST GAPS` / `== TEST SMELLS`
  (printed by test_gaps.py), `== ERROR HANDLING` (printed by
  check_errors.py), and `== CI RESULT`.
  - **CI exit policy:** exit 1 on new architecture violations at or above
    `--fail-on`, or on analyzer errors in scope. Analyzer errors only count
    when `.dart_tool/package_config.json` exists. Test gaps, error-handling
    findings and candidates never fail CI.
  - When check_errors runs, the heuristic `swallowed-catch` line keeps only
    its count and says "see ERROR HANDLING".
  - The action's entry point is `skills/dart-flutter-review/scripts/ci_action.sh`.
- **action.yml:**
  - Inputs: `path`, `base-ref`, `fail-on`, `baseline`, `flutter`, `flutter-version`.
  - Outputs: `new-violations`, `report-path`.
  - `uses: …@v1` requires a moving `v1` tag.
- **test_gaps.py:**
  - JSON keys: `schema` (`flutter-pro-skills/test-gaps@1`), `profile`
    (+`classifier`, `classifier_note`), `units`, `gaps`, `smells`, `stats`.
  - Gap IDs are `TEST-untested-{repository,usecase,logic,source,service,view,widget}`.
  - There's an extra info smell, `TEST-preview-only`, for screenshot tests that
    save images without asserting.
  - Only `test/` is credited to units.
- **check_errors.py:**
  - JSON keys: `schema` (`flutter-pro-skills/error-check@1`), `root`,
    `package`, `profile`, `classification`, `stats`, `findings` (note: not
    `violations`), `suppressed`.
  - Severities include `info`.
  - Rules:
    - ERR-001 swallowed-catch (graded by context: high, medium, low or info)
    - ERR-002 untyped-catch-unmapped
    - ERR-003 catches-error
    - ERR-004 repository-leaks-transport-exception (network transport only, reported per repository)
    - ERR-005 throws-non-exception
    - ERR-006 domain-throws-transport
    - ERR-007 repository-null-on-failure
    - ERR-008 raw-error-shown-to-user
    - ERR-009 mixed-result-and-throw
    - ERR-010 loading-without-error-path
    - ERR-011 rethrow-loses-stack
    - ERR-012 missing-global-error-handler (reported once per project)
    - ERR-013 zone-mismatch
  - `--files` accepts a list file or a comma-separated list.
- **scaffold.py:**
  - Profiles: mvn, mvvm, bloc, cubit, getx, provider, riverpod, each with
    `--clean`, in both layouts.
  - `--force-dir` is required to add files to an existing feature folder.
  - It detects riverpod_generator ≥3 provider naming from pubspec.lock.
  - On SDK ≥3.12 it uses private named initializing formals.
  - Plain Riverpod gets a per-feature `di/<f>_providers.dart`.
  - MVVM `--clean` puts the repository contract in `domain/`.
  - `SCAFFOLD_SKIP_COMPILE=1` skips the real compile tests.
- **Known limitation:** a plain-Riverpod app with ≥3 `*Notifier extends _$X`
  classes is detected as `mvn`. Pass `--profile riverpod`.

---

# Phase 3 contracts (v1.0.0 public release)

## 14. New skills, ownership, release version

The first public release is **v1.0.0**. Every skill's `metadata.version`
is `"1.0.0"`; the lead normalises existing skills at the end.

| Owner (phase 3, wave 1) | Files |
|---|---|
| Agent S | `skills/flutter-architecture/references/**` and the references table in `skills/flutter-architecture/SKILL.md` |
| Agent N1 | `skills/flutter-navigation/**` (new) |
| Agent N2 | `skills/flutter-forms/**` (new) |
| Agent N3 | `skills/flutter-i18n/**` (new) |
| Agents K1–K3 | nothing in the repo: they **read only**, and clone public apps into their own scratch folders |

The new skills follow §2: portability rules, frontmatter, descriptions of
≤1024 characters (target ≤900), python3 stdlib, bash 3.2, read-only scripts,
`tests/run.sh`, and `metadata.suite: flutter-pro-skills`.

New finding-ID prefixes:
- `NAV-0xx` (script) / `NAV-<slug>` (reading)
- `FORM-0xx` / `FORM-<slug>`
- `I18N-0xx` / `I18N-<slug>`

**Optional script per new skill.** A skill may ship one read-only checker:

```
python3 -I scripts/<check_x>.py <project-root> [--json] [--files <list-file-or-comma-list>] [--profile <p>] [--max n]
```

- Text output starts with a single header line: `== NAVIGATION`, `== FORMS`
  or `== I18N`.
- Groups are `  [NAV-0xx] name (sev) xN — message`, followed by
  `      file:line  evidence` lines.
- JSON follows the schema `flutter-pro-skills/<skill>@1`, with the keys
  `schema`, `root`, `package`, `profile`, `stats`, `findings` (each finding
  has `id`, `name`, `severity`, `file`, `line`, `evidence`, `message`, `note`)
  and `suppressed`.
- Suppress with `// nav-ignore: NAV-0xx <reason>` (likewise `form-ignore`,
  `i18n-ignore`), on the line or as `-file:` for the whole file.
- For layer and role, read `../flutter-architecture/scripts/arch_check.py --json`
  (its `files[]`), with a fallback.

**No duplicate rules.** Before adding a rule, check whether the suite already
covers it, and cross-reference instead of re-implementing:
- ARCH-102 / AP-navigation-in-logic: navigation in logic
- `use_build_context_synchronously` / UI-context-after-await: `context` after `await`
- the `undisposed-resource` heuristic and UI-lifecycle: undisposed controllers
- ARCH-109: ephemeral state in providers

**Official recipes.** `flutter/agent-plugins` has
`flutter-setup-declarative-routing` and `flutter-setup-localization`
(BSD-3). Defer to them for step-by-step setup ("if installed"). Our skills
add per-architecture placement, review checklists and checkers.

## 15. Splitting anti-patterns.md (Agent S)

- `references/anti-patterns.md` becomes the **index**:
  - the Contents list
  - the index table with every ID's severity, profiles and detection, plus a
    link to the group file
  - a one-paragraph summary per group
- Entries move to `references/anti-patterns/<group>.md`, where `<group>` is
  one of `dependency-rule`, `presentation`, `state`, `data-and-repositories`,
  `di-and-globals`, `over-engineering` or `pattern-specific`. Each entry keeps
  its `### <ID> <name>` heading verbatim, so `grep -rn '^### ARCH-005'
  references/` still finds it.
- This is a deliberate exception to "references one level deep". The index
  is the one level the agent reads first, and it links each group file.
- Update every in-repo link that points to `anti-patterns.md#…` or says
  "anti-patterns.md § ID" (grep across `skills/`) so it still resolves. Edit
  other skills' files **only** for those link fixes.

## 16. Calibration reports (K1–K3 → wave-2 fixers)

Each calibration agent returns, as text in its final message, one section per
tool (arch_check, check_errors, test_gaps, review.sh heuristics). Each
section holds:
- the app, its commit and its detected profile
- per-rule hit counts, with TP/FP judged by reading the code
- for every FP **cause** (not every hit):
  - the rule
  - a minimal Dart repro (≤25 lines)
  - why it's a false positive under that pattern's own rules (cite the
    canonical source: the Flutter guide, bloclibrary, riverpod.dev, the MVN
    spec)
  - the suggested fix
- false negatives it noticed: real anti-patterns the tools missed

The scratch paths of the clones are kept, so fixers can re-run the tools.

## 17. Clean and secure by default (suite positioning)

The suite's promise is that **code an agent writes with these skills is clean
and secure by default**: correct for the app's architecture *and* safe without
a later hardening pass.

- New skill **`flutter-secure-defaults`** (Agent N4) owns `skills/flutter-secure-defaults/**`.
  - **What it covers:** write-time security defaults, placed per layer and per
    architecture. That means where tokens and credentials live (the data
    layer, platform secure storage), no secrets in source or `--dart-define`
    defaults, HTTPS only, auth interceptors in services, no PII or tokens in
    logs, error messages, analytics or crash reports, input validation at
    boundaries, deep-link and URL validation, safe WebView defaults, minimal
    permissions, and release-build flags.
  - **Its checker:** `scripts/check_secure_defaults.py`, with the §14 CLI and a
    `== SECURITY DEFAULTS` header. IDs are `SEC-0xx` for checker rules and
    `SEC-<slug>` for findings from reading the code.
  - **Defers to `flutter-security-audit`.** That's a separate, existing skill by
    the same author, covering RASP, obfuscation, pinning, attestation and
    build hardening, with MASVS/CWE tags. Load it if it's installed and run
    its `scan.sh` for deep audits. Don't duplicate its checks; cross-reference
    them.
- **Every other skill keeps security in scope where it naturally belongs:**
  - navigation: deep-link validation and auth guards
  - forms: `obscureText`, autofill hints, no logging of field values, server-side
    validation reminders
  - error handling: no secrets or PII in error text (already ERR-008)
  - scaffold: secure templates, wave 2
  - review: a security pass, wave 2

## 18. Calibration fixes (phase 3, wave 2): shared decisions

Fixers work from the calibration reports K1–K3 (kept outside the repo; the clones of the public apps sit next to them).
The rule is that the canonical reference apps must come out clean:
- flutter/samples compass_app (MVVM)
- the felangel/bloc examples
- the rrousselGit/riverpod examples

| Owner (wave 2) | Files |
|---|---|
| FX-A | `skills/flutter-architecture/**` (scripts, tests, and the FP or semantics notes in references) |
| FX-E | `skills/flutter-error-handling/**` |
| FX-T | `skills/flutter-testing/**` |
| FX-R | `skills/dart-flutter-review/**` |

**New `files[].role` values** (FX-A adds them; every consumer must also accept unknown roles):
- `repository`: a concrete `*Repository` with no contract anywhere. Consumers treat it like `repository-impl` for gaps and ERR-004/007/009.
- `barrel`: only directives, no declarations. Consumers skip it.
- `di`: top-level providers only, or a `*Factory`/`*Module`/`*Locator` that only constructs objects. Consumers treat it like the composition root and skip it.
- ChangeNotifier subclasses that aren't `*Repository` or `Command*`, and classic Riverpod notifiers (`StateNotifier`, `Notifier`, `AsyncNotifier`), are `logic` in every profile.

**MVN detection** follows K3's rule: use cases are required (`presentation/notifier(s)/` plus use cases means high). The profile signals add `use cases: N files`.

**Generated-file detection lives in arch_check only.** `files[]` is the source of truth for scope. review.sh, check_errors and test_gaps should use it when it's present. The new skills' checkers already read it.

**One report per import.** When ARCH-005 and ARCH-008, or ARCH-007 and ARCH-012, fire on the same import line, arch_check keeps the more specific or higher-severity one and notes the other ID in `note`.

Every fix lands with a regression fixture built from the report's minimal repro, plus a test asserting the FP no longer fires. Where the report shows a true positive, add a test asserting it still fires.

## 19. Phase 3 as built (these entries win over §14–18)

- **New checkers.** These are their JSON schemas. Each adds a
  `classification` key to the §14 keys.
  - `flutter-navigation@1`: NAV-001…012, plus a `rules.md` reference
  - `forms@1`: FORM-001…008
  - `i18n@1`: I18N-001…006, 010…018. It also reads easy_localization and slang
    catalogs, and suppression inside a catalog uses the `"@@x-i18n-ignore"` key.
  - `flutter-secure-defaults@1`: SEC-001…012, plus a `deep_audit` key
- **Ownership dedupe:**
  - NAV-005/006 own the url_launcher allow-list and PII in URLs. SEC doesn't
    re-implement them.
  - FORM-004 owns the logging of form-field values. SEC-004 skips those.
  - When check_i18n ran, I18N-010 replaces UI-l10n and I18N-012 replaces UI-rtl.
- **ID collision note:** flutter-security-audit's scan.sh uses `SEC-HARDCODED`
  and `SEC-CLOUDKEY` (uppercase words). Our script IDs are always numeric
  (`SEC-0xx`), and our reading IDs are lowercase slugs (`SEC-no-logout-wipe`).
  Keep scan.sh IDs verbatim when merging, and dedupe by file:line.
- **check_errors:**
  - New rule **ERR-014 unguarded-io-in-ui** (medium).
  - ERR-010 now covers State classes too, and `finally` resets plus Result typedefs count as handled.
  - New stats keys: `skipped_roles`, `skipped_out_of_scope`.
- **test_gaps:**
  - New smell `TEST-tests-the-mock` (medium).
  - New stats keys: `skipped`, `path_packages`.
  - New text lines: `not units:` and `path packages …`.
- **review.sh:**
  - New sections:
    - `== SECURITY DEFAULTS`
    - `== SECURITY AUDIT` (runs scan.sh when the sibling skill or `$FLUTTER_SECURITY_AUDIT_SCAN` is present; it is informational and never fails CI)
    - `== NAVIGATION`, `== FORMS`, `== I18N`
  - New flags: `--no-security`, `--no-audit`, `--no-nav`, `--no-forms`, `--no-i18n`, and a generic `--skip <list>`.
  - Environment handling:
    - pub workspace detection: walks up to the package_config that lists the package
    - codegen-cascade collapse: cascade errors are excluded from CI
    - SDK-constraint skip
    - analyzer-crash status line
  - Scope comes from arch_check `files[]`.

## 20. Release v1.0.0 as built

- **Every skill is versioned 1.0.0.** `tests/validate_skills.py` also rejects
  descriptions that aren't valid strict YAML (an unquoted `: ` or ` #`),
  because strict parsers in some agents would refuse the skill.
- **Descriptions were tuned for routing between siblings** (scratch eval set,
  D1). Each says when to load a sibling instead, which reduces misroutes such
  as "review my tests" going to review instead of testing.
- **Scaffold** writes app-wide `lib/core/error/failure.dart` and
  `lib/core/network/http_client.dart` (GetX: `api_client.dart` on an injected
  `GetConnect`) once, and reuses them. Generated code gets 0 findings from the
  security, architecture, error and forms checkers, enforced in tests.
- **arch_check, after the benchmark:**
  - It no longer reports `material` imports used only for value types
    (`Color`, `DateTimeRange`…).
  - A view importing another feature's view (navigation) is never ARCH-014.
  - Under bloc, a view importing another feature's bloc, cubit, state or
    event is not ARCH-014 (bloclibrary connects blocs through the UI).
  - Under bloc, navigation-only feature cycles are not ARCH-015.
  - The regression fixture is `calib_bloc_weather`.
- **`FPS_ARCH_JSON`:** review.sh runs `arch_check --json` once and exports the
  path. Every sibling checker reuses it when the `root` matches and the forced
  profile, if any, matches.
- **`bench/`** holds a reproducible with/without-skills harness. See
  `bench/README.md` for the results and limitations.

---

# Phase 4 contracts (v1.1.0)

## 21. Plan: four new skills

v1.1.0 closes the remaining coverage gaps (performance, persistence, design
system, accessibility). Each gap becomes its own skill, with the same shape as
the phase 3 skills: architecture-aware guidance, secure-by-default writing, and
one read-only checker that `dart-flutter-review` runs.

| Skill | Scope | Prefix | Checker | Header | JSON schema | Suppression |
|---|---|---|---|---|---|---|
| `flutter-performance` | rebuild scope per pattern, `const`, `RepaintBoundary`, lazy lists and slivers, isolates and `compute`, image decode sizing, `saveLayer` costs, jank diagnosis with DevTools (profile mode, timeline, raster vs UI thread) | `PERF-0xx` / `PERF-<slug>` | `scripts/check_performance.py` | `== PERFORMANCE` | `flutter-pro-skills/performance@1` | `perf-ignore` |
| `flutter-persistence` | Drift, sqflite, Hive/Isar, shared_preferences, flutter_secure_storage, caching policy, offline-first and sync, migrations, and where each sits in MVN, MVVM, Bloc and Clean | `PERSIST-0xx` / `PERSIST-<slug>` | `scripts/check_persistence.py` | `== PERSISTENCE` | `flutter-pro-skills/persistence@1` | `persist-ignore` |
| `flutter-design-system` | tokens (colour, type, spacing, radius, elevation, motion), `ThemeData` + `ColorScheme`, `ThemeExtension`, component structure, dark mode, no raw colours or sizes in feature code | `DS-0xx` / `DS-<slug>` | `scripts/check_design_system.py` | `== DESIGN SYSTEM` | `flutter-pro-skills/design-system@1` | `ds-ignore` |
| `flutter-accessibility` | `Semantics`, labels, tap targets, contrast, text scale, focus and traversal, screen-reader and `meetsGuideline` tests | `A11Y-0xx` / `A11Y-<slug>` | `scripts/check_accessibility.py` | `== ACCESSIBILITY` | `flutter-pro-skills/accessibility@1` | `a11y-ignore` |

**Ownership (build phase).** Never edit a file you don't own; put requested
changes in your final report.

| Owner | Files |
|---|---|
| Lead | this section, root files, `tests/`, `install.sh`, `README*.md`, `CHANGELOG.md`, the hub routing table, `skills/dart-flutter-review/**` (integration), `metadata.version` bumps |
| Agent P1 | `skills/flutter-performance/**` |
| Agent P2 | `skills/flutter-persistence/**` |
| Agent P3 | `skills/flutter-design-system/**` |
| Agent P4 | `skills/flutter-accessibility/**` |

## 22. What every new skill ships

- **`SKILL.md`** that follows §2. The frontmatter has `name` equal to the
  folder, `license: MIT`, `metadata.author: abdelrahman-abied`,
  `metadata.version: "1.1.0"` and `metadata.suite: flutter-pro-skills`. The
  `description` is **≤900 characters** and valid strict YAML: no unquoted `: `
  or ` #` (`tests/validate_skills.py` enforces this). It says what the skill
  does, when to use it (pushy, keyword-rich), and which sibling to load
  instead for neighbouring concerns (§20 routing).
- **The body**, which must include:
  - **Architecture placement.** Say where each concern lives in MVN, MVVM,
    Bloc/Cubit, Clean, Provider, GetX and Riverpod. Detect the pattern by
    running `../flutter-architecture/scripts/arch_check.py --json`, or by
    reading the project, and judge by that pattern's own rules (§3
    precedence).
  - **Secure by default.** Cover the security concern that naturally belongs
    to the skill, and cross-reference `flutter-secure-defaults` for the rest.
  - **Review checklist.** Give the finding IDs with severities and a concrete
    fix each, in the §4 format.
  - **Deference to the official recipes.** Defer to `flutter/agent-plugins`
    and `dart-lang/skills` where a step-by-step recipe exists ("if
    installed").
- **`references/`**, one level deep. Any file over 300 lines starts with
  `## Contents`. It must include `references/rules.md`, which documents
  every checker rule: what it detects, its severity, why it matters, a
  bad/good Dart example, the profile notes, the known false positives and the
  suppression.
- **One read-only checker** with the §14 CLI:
  `python3 -I scripts/check_<x>.py <project-root> [--json] [--files <list-file-or-comma-list>] [--profile <p>] [--max n]`.
  - **Runtime.** Use stdlib only. It must parse as Python 3.8
    (`ast.parse(..., feature_version=(3, 8))`).
  - **Exit codes.** Exit 0 when the report is produced, including when there
    are findings. Exit 2 on a usage error: no `pubspec.yaml`, an unknown
    option or an unknown profile. With no `lib/`, print an empty report and
    exit 0.
  - **Classification.** Use arch_check `files[]` (§10, §18): reuse
    `$FPS_ARCH_JSON` when its `root` matches and any forced profile matches
    (§20), otherwise run arch_check as a subprocess.
    - Never import arch_check's internals.
    - When arch_check is missing, fall back to path-based classification and
      say so in `classification`.
    - Accept unknown roles. Skip `barrel`, `di` and generated files.
  - **Text output.** Start with the header line from §21, then
    `  profile: …`, `  classification: …` and a `  scanned: …` line.
    - Each group is `  [ID] name (sev) xN — message`, followed by
      `      file:line  evidence` lines and `      ... N more` when there are
      more than `--max`.
    - With no findings, print `  no <area> findings`.
    - End with `  suppressed: N (see --json)` when anything was suppressed.
  - **JSON output.** Use the keys `schema`, `root`, `package`, `profile`
    (`presentation`, `source`), `classification`, `stats` (`files` at least),
    `findings` and `suppressed`.
    - Each finding has exactly `id`, `name`, `severity`, `file`, `line`,
      `evidence`, `message` and `note`.
    - Severities are high, medium, low or info.
    - The `note` carries the profile-specific fix where one exists (e.g.
      `MVN: …`, `Bloc: …`).
  - **Suppression.** Honour `// <prefix>-ignore: ID <reason>` on the line or
    the line above, and `// <prefix>-ignore-file: ID <reason>` anywhere in
    the file. Keep the reason.
  - **Rule budget.** Aim for 6–12 rules. A rule ships only if it is cheap to
    explain, has a precise fix, and survived calibration (§23). Judgement
    calls that a regex can't make reliably become documented `<PREFIX>-<slug>`
    reading-level findings, not checker rules.
- **`tests/run.sh`** (§8). It needs no Flutter SDK, prints `PASS`/`FAIL`
  lines, exits 1 on failure, and is bash 3.2 safe. It covers:
  - the Python 3.8 parse
  - a `violations` fixture where every rule fires (with severities and notes
    asserted)
  - a `clean` fixture with zero findings, built from the near-misses
  - a `suppressed` fixture
  - read-only, checked with a before/after checksum of the fixture
  - the JSON contract keys, the text format and `--max` collapsing
  - `--files` as a list file and as a comma list
  - the fallback without the arch_check sibling (copy the script into a temp
    folder)
  - a `--profile` override changing the `note`
  - the exit-2 cases, and no `lib/`
  - one `calib_<app>` regression fixture per false-positive cause fixed during
    calibration, with a test that the FP no longer fires, plus a test that
    the related true positive still fires

## 23. No duplicate rules: who owns what

Before adding a rule, check §6, §13, §19 and the heuristics in
`dart-flutter-review/scripts/heuristics.py`. Cross-reference instead of
re-implementing. The ownership below is binding:

| Concern | Owner (stays there) | New skill's role |
|---|---|---|
| `MediaQuery.of(context).x`, `UniqueKey()` in build, FutureBuilder future made in build, widget-helper methods | heuristics `mediaquery-of`, `unique-key`, `future-in-build`, `widget-helper-method` / `UI-*` | PERF references them; doesn't re-detect them |
| Eager `children: list.map(...)` lists, `Opacity` widget | **moves to PERF** (more precise rules). When check_performance ran, heuristics `eager-children-map` and `opacity-widget` keep only their count and point at PERFORMANCE (like `defer-catch`) | PERF-0xx owns them |
| `UI-image-decode-size`, `UI-blocking-ui-isolate`, `UI-rebuild-scope` | PERF-0xx beats these UI slugs for the same file and line | |
| Hard-coded `Color(0x…)` outside theme files | **moves to DS**. When check_design_system ran, the heuristic `hardcoded-color` keeps only its count and points at DESIGN SYSTEM | DS-0xx owns colour, type, spacing and radius literals; DS beats `UI-hardcoded-style` |
| `EdgeInsets.only(left:)`, physical direction | I18N-012 | DS ignores direction, and judges only magic numbers |
| `UI-a11y` | A11Y-0xx beats it for the same file and line | |
| Hard-coded label strings | I18N-010 | A11Y flags a *missing* label, never a non-localised one |
| Autofill hints, obscured fields | FORM-001/002/003 | A11Y doesn't re-check them |
| Tokens and credentials in SharedPreferences, Hive or global state | SEC-001 / SEC-010 | PERSIST cross-references them and doesn't re-detect them |
| `SharedPreferences.getInstance(` / `openDatabase(` in widgets; I/O-package imports in UI or logic | ARCH-101 / ARCH-005 / ARCH-007 / ARCH-012 | PERSIST judges what arch can't: migrations, schema, queries, cache policy |
| Swallowed or unmapped storage errors | ERR-001/002/004/007 | PERSIST doesn't re-detect catches |
| `print` / log of values | SEC-004, FORM-004 | |
| `material.dart` imported by logic | ARCH-009 (which exempts value-only uses such as `Color`) | DS may own "visual tokens held in logic/state" (a `Color`, `TextStyle` or `IconData` field in a logic or state file), because ARCH-009 deliberately no longer reports it |

When a new checker ran, its ID beats the overlapping reading-level slug for
the same file and line, and the dropped ID is cited in `rule:`. The lead adds
these rows to `dart-flutter-review/references/finding-format.md`.

## 24. Calibration (each agent does its own, before handing in)

- **The apps.** A shared pool is cloned read-only (shallow) under the lead's
  scratch folder `calib/` (path given in the agent brief). It contains
  `samples` (flutter/samples, canonical: `compass_app`), `bloc` (canonical:
  `examples/*`), `riverpod` (canonical: `examples/*`), `lichess`
  (lichess-org/mobile), `wonderous` (gskinnerTeam/flutter-wonderous-app),
  `drift` (simolus3/drift, `examples/app`) and `immich` (`mobile/`).
- **Coverage.** Run on all three canonical sets plus **at least two**
  non-canonical apps that exercise the skill's domain: persistence uses drift
  and immich, design-system and accessibility use wonderous, performance uses
  immich and lichess.
- **Read-only.** Never modify a clone. `git -C <clone> status --porcelain` is
  empty afterwards. Extra clones go in your own scratch folder, never in the
  repo.
- **How to judge.** Read the code behind every high and medium hit and judge
  it TP or FP by the pattern's canonical source. Fix every FP *cause*.
- **Exit criterion.** **The canonical apps have zero high or medium false
  positives.** Low and info hits on canonical apps are allowed only if each is
  a defensible true positive.
- **What to report.** Add a short "Calibration" table to
  `references/rules.md`: app, commit, per-rule hits and TP/FP. Use no local
  paths, only `org/repo@sha`. The final message to the lead holds the same
  table, the regression fixtures added, and any change you need in files you
  don't own.

## 25. Review integration (lead, after the agents finish)

- **New review.sh sections.** They run after I18N, in this order:
  `== PERFORMANCE`, `== PERSISTENCE`, `== DESIGN SYSTEM`, `== ACCESSIBILITY`.
  All four are informational and never fail CI.
- **New flags.** `--no-perf`, `--no-persist`, `--no-ds` and `--no-a11y`, plus
  `--skip` keys `perf,persist,ds,a11y`.
- **Heuristic deferral.** `heuristics.py grep` gains `defer-perf` (for
  `eager-children-map` and `opacity-widget`) and `defer-ds` (for
  `hardcoded-color`).
- **Reviewer passes.** `reviewer-prompts.md` gets four new optional passes
  (performance, persistence, design system, accessibility), and §23's
  overlap rows go into the dedupe rules.
- **The rest of the suite.** Add the hub routing rows, extend `install.sh`
  `ALL_SKILLS` to sixteen, update the README (English and Arabic) and the
  CHANGELOG `[1.1.0]`, and bump every skill's `metadata.version` to `"1.1.0"`.

## 26. Phase 4 as built (these entries win over §21–25)

- **Checkers and rules:**

  | Checker | Rules |
  |---|---|
  | `performance@1` | PERF-001…011 |
  | `persistence@1` | PERSIST-001…009, plus 11 reading slugs |
  | `design-system@1` | DS-001…012, plus 9 reading slugs |
  | `accessibility@1` | A11Y-001…011 |

  Each checker's `references/rules.md` holds the rule catalog and a
  Calibration table. All four add the `classification` key.
- **"List item" (PERF):** the code inside a lazy list or grid `itemBuilder`
  or `*BuilderDelegate`, plus one hop into a project widget built there.
  `PageView` items are excluded.
- **Ownership additions to §23:**
  - PERF-010 (sort in build) beats `UI-build-side-effect` for that case only.
  - PERSIST-009 (sensitive data in unencrypted stores) deliberately excludes
    tokens and passwords, which stay SEC-001.
  - A11Y-008 owns contrast ratios and A11Y-004 owns text scale, while DS owns
    token structure.
- **Design-system scales:**
  - DS-003 and DS-004 fire only when the app has a spacing or radius scale
    of at least 3 distinct steps.
  - DS-001 and DS-002 are graded info when the app has no design system at
    all.
- **Persistence's own generated-file detection:** the persistence checker
  detects generated files itself, for drift's `*.drift.dart` modular output.
  arch_check's banner regex no longer treats drift's
  "Generated by drift_dev when running build_runner" note in a hand-written
  file as a generated banner. The regression test is in
  `calib_riverpod_features`.
- **review.sh:**
  - Sections and flags are as in §25.
  - `heuristics.py grep` takes any of `defer-catch`, `defer-perf` and
    `defer-ds`.
  - The step summary lists the new sections.
- **Calibration result:**
  - The canonical apps (compass_app, the bloc examples, the riverpod
    examples) have **zero high or medium false positives** in all four
    checkers.
  - Their remaining medium hits are A11Y-001/002/005/008, all true positives
    on reading:
    - icon-only FABs and IconButtons without a tooltip
    - an `InkWell` wrapping only an icon, with no `Semantics` anywhere in
      compass
    - a 40 dp tap target
    - white on red at 3.68:1
  - The non-canonical apps were immich, lichess, wonderous and the drift
    examples.

---

# Phase 5 contracts (v1.2.0)

## 27. flutter-networking

**What it covers.** The API layer in each architecture:
- clients: `http`, Dio, retrofit, chopper, generated OpenAPI clients
- configuration: base options, timeouts, interceptors and their order
- data: DTOs and JSON (`json_serializable`, `freezed`, validating
  `fromJson`), and mapping DTOs to entities
- requests: pagination (cursor or page, plus an in-flight guard),
  cancellation (`CancelToken`, `ref.onDispose`, `close()`), retry with
  backoff (idempotent methods only)
- environment: connectivity as a hint, uploads, downloads and progress,
  WebSockets
- testing: fake HTTP clients and adapters

**Where each part sits.** The remote source sits in `data/`. The repository
maps DTOs to entities and transport errors to failures. MVN use cases, MVVM
view models and blocs never see a client or a DTO.

**Contract values.**

| Item | Value |
|---|---|
| Owner | Agent P5: `skills/flutter-networking/**` |
| Prefix | `NET-0xx` / `NET-<slug>` |
| Checker | `scripts/check_networking.py` (§22 CLI and output contract) |
| Header | `== NETWORKING` |
| Schema | `flutter-pro-skills/networking@1` |
| Suppression | `net-ignore` |

**No duplicates.** These rules already exist, so the skill cross-references
them and never re-detects them:

| Concern | Owner |
|---|---|
| Auth headers outside the data layer | SEC-002 |
| Cleartext `http://` | SEC-003 |
| HTTP loggers in release | SEC-005 |
| Accept-any-certificate | SEC-006 |
| Bodies logged | SEC-011 |
| Token storage | SEC-001 |
| Clients or I/O in widgets and logic | ARCH-005 / 007 / 101 / 012 |
| Repositories returning `Response` / `Map` / DTOs | ARCH-107 |
| Transport exceptions escaping repositories | ERR-004 |
| Unguarded I/O in UI | ERR-014 |
| Large JSON decoded on the UI isolate | PERF-011 |
| Cache policy and connectivity-as-truth | PERSIST-* |
| Untrusted URL launches | NAV-005 |
| Pinning | flutter-security-audit |

**Secure by default.** The client is configured once. It has timeouts set.
Retries happen only for idempotent requests. Server data is validated at the
DTO boundary, never trusted.

**Review integration (lead).**
- `== NETWORKING` runs after `== PERSISTENCE`, with `--no-net` and the
  `--skip` key `net`. It is informational.
- Reviewer Template N is added, and the dedupe rows go in `finding-format.md`.

**Calibration (§24).**
- **Canonical apps:** compass_app, `bloc/examples/flutter_infinite_list`,
  and `riverpod/examples/{marvel,pub,stackoverflow,first_app}`.
- **Non-canonical apps:** hiddify (Dio), lichess (`http`) and immich
  (generated client and `http`).
- **Exit criterion:** zero high or medium false positives on the canonical
  apps.

## 28. Phase 5 as built: v1.2.0 (these entries win over §27)

- **Release.** v1.2.0 has seventeen skills, and every skill's
  `metadata.version` is `"1.2.0"`.
- **Rules.** `networking@1` has NET-001…010:
  - NET-001 client-without-timeouts
  - NET-002 client-created-per-call
  - NET-003 http-client-never-closed
  - NET-004 retry-resends-any-method
  - NET-005 page-fetch-without-guard
  - NET-006 cancel-token-never-cancelled
  - NET-007 websocket-never-closed
  - NET-008 base-url-duplicated (automates `AP-hardcoded-config-in-sources`
    for API hosts)
  - NET-009 top-level-http-call
  - NET-010 query-value-not-encoded

  There are also 8 reading slugs. The stats keys are `packages`,
  `dio_clients`, `http_clients`, `interceptors`, `websockets`,
  `cancel_tokens`, `page_handlers` and `skipped_generated`. The checker also
  skips files with an OpenAPI Generator banner.
- **ID collision note** (like §19). `flutter-security-audit`'s `scan.sh` uses
  upper-case `NET-ACCEPT-ALL` and `NET-CLEARTEXT`. Ours are numeric
  (`NET-0xx`) or lower-case slugs. A `scan.sh` NET id becomes `SEC-<slug>` in
  a report.
- **Ownership.**
  - The retry policy in the HTTP client is NET-004's. Offline replay belongs
    to PERSIST, and each side only cross-references the other.
  - NET-004 beats `ERR-retry-non-idempotent`.
  - NET-007 beats the `undisposed-resource` candidate for the same line.
- **Calibration.**
  - **Canonical apps:** zero high or medium false positives. The 4 medium
    NET-001 hits in the riverpod examples are true positives, because a
    plain `Dio()` has no timeouts.
  - **Non-canonical apps:** hiddify (Dio, GPL), lichess and immich. Their
    fixtures are fresh minimal repros, with no copied lines.
- **Scaffold.** The generated files get zero findings from all five v1.1+
  checkers (performance, persistence, networking, design system,
  accessibility), enforced in the scaffold tests.
- **Benchmark.** Task T4 (a product list screen) is scored by
  `grade.py t4`. `all.sh` takes a `TASKS` variable.

---

# Phase 6 contracts (v1.3.0)

## 29. flutter-release

**Scope.** Getting a Flutter app from the repo to the stores, safely and
repeatably:
- flavors and environments (Android `productFlavors`, iOS schemes and
  xcconfigs, `main_<flavor>.dart` or `--dart-define-from-file`)
- environment config read once at the composition root and injected, never
  read in features
- signing (upload keystore and `key.properties` kept out of the repo,
  Play App Signing, iOS certificates and profiles via CI secrets)
- versioning (`version: x.y.z+build`, a monotonically increasing build
  number)
- release build flags (`--release`, `--split-debug-info`; obfuscation itself
  belongs to SEC-012 and flutter-security-audit)
- store requirements (`applicationId`/bundle id, target SDK level, iOS privacy
  manifest, permission usage strings)
- CI/CD (GitHub Actions, Codemagic, Fastlane): a pinned Flutter version,
  cached pub, secrets handled safely, no `pull_request_target` running
  untrusted code with secrets, and build artifacts that never contain the
  keystore
- release checklists and staged rollouts

**Architecture placement.** Flavor and environment selection belongs to the
composition root (`main_*.dart`, `app/`, `di/`). The data layer receives
`baseUrl` and keys through DI. Logic and views never branch on the flavor.
The patterns differ only in how the environment is injected: Riverpod
override, get_it registration, `RepositoryProvider`, a constructor.

**Contract values.**

| Item | Value |
|---|---|
| Owner | Agent P6, `skills/flutter-release/**` |
| Prefix | `REL-0xx` / `REL-<slug>` |
| Checker | `scripts/check_release.py`. The §22 CLI and output contract apply. Unlike the other checkers, it also reads `android/**/build.gradle(.kts)`, `android/key.properties`, `ios/**/Info.plist`, `ios/**/*.xcconfig`, `ios/Runner/PrivacyInfo.xcprivacy`, `pubspec.yaml`, `.gitignore`, `.github/workflows/*.y*ml`, `codemagic.yaml` and `fastlane/**`. Findings in those files report the project-relative path. `--files` filters by path like the others |
| Header | `== RELEASE` |
| Schema | `flutter-pro-skills/release@1` |
| Suppression | `rel-ignore`, as a `//` or `#` comment in Dart, Gradle, YAML or xcconfig files |

**App-aware by default.** A sample or example app (`publish_to: none` with
`com.example` ids, no store metadata, or an examples folder) gets info at
most for store-readiness rules. The rules apply in full when the project
shows release intent: a changed `applicationId`, flavors, a fastlane or
codemagic config, a release workflow, or signing configs.

**No duplicates.** Cross-reference these; never re-detect them:

| Concern | Owner |
|---|---|
| Hard-coded secrets, and secrets in build config or `--dart-define` defaults | SEC-008 / SEC-009 |
| Obfuscation and `--split-debug-info` absence | SEC-012 |
| HTTP loggers in release | SEC-005 |
| Cleartext URLs | SEC-003 |
| Router debug logging in release | NAV-011 |
| Debuggable, `allowBackup`, ATS arbitrary loads, pinning, RASP | flutter-security-audit (`scan.sh`) |
| Base URLs duplicated across sources | NET-008 |
| `print` calls | `avoid_print` lint |

**Review integration (lead).** `== RELEASE` runs after `== ACCESSIBILITY`,
with `--no-release` and the `--skip` key `release`. It is informational and
never fails CI. Add reviewer Template O and the dedupe rows. Bump the release
to v1.3.0: eighteen skills, fourteen checkers.

**Calibration (§24).**
- **Canonical apps** (zero high or medium false positives):
  - compass_app
  - the bloc examples and riverpod examples (samples: store-readiness rules
    must stay quiet)
  - `news_toolkit/flutter_news_example` (Flutter team and VGV, real
    flavors; BSD)
- **Non-canonical apps:** `io_flip` (VGV, BSD), immich (fastlane, GitHub
    Actions; AGPL), lichess (fastlane; GPL) and hiddify (CI; GPL).
- **Fixtures for copyleft apps** are fresh minimal repros with no copied
    lines.

## 30. Phase 6 as built: v1.3.0 (these entries win over §29)

- **Release.** v1.3.0 has eighteen skills and fourteen checkers. Every
  `metadata.version` is `"1.3.0"`.
- **Rules.** `release@1` has REL-001…012:
  - REL-001 release-signed-with-debug-key
  - REL-002 signing-file-not-ignored
  - REL-003 placeholder-application-id
  - REL-004 flavor-mismatch
  - REL-005 environment-by-build-mode
  - REL-006 flavor-read-outside-root (automates
    `AP-hardcoded-config-in-sources` for environment reads)
  - REL-007 debug-switch-left-on
  - REL-008 target-sdk-below-play-minimum (`PLAY_MIN_TARGET_SDK = 35`, a
    dated constant)
  - REL-009 usage-description-missing
  - REL-010 pr-target-runs-untrusted-code
  - REL-011 secret-printed-in-ci
  - REL-012 signing-key-exposed-in-ci

  There are also 8 reading slugs. Pinned Flutter in CI, top-level
  `permissions:` and the iOS privacy manifest are reading-level only.
- **Files read** (in addition to §29):
  - `ios/Runner.xcodeproj/project.pbxproj` (bundle ids and native targets)
  - `ios/Runner.xcodeproj/xcshareddata/xcschemes/*.xcscheme`
  - every `.gitignore` up to the repo root
  - repo-root `.github/workflows` and `codemagic.yaml` when they mention the
    project. These are reported with `../` paths.
- **App-aware (correction to §29).** A changed `applicationId` alone is not
  release intent. Release intent needs one of:
  - a release signing config
  - flavors
  - a fastlane or codemagic config
  - a release workflow

  An `examples/` or `samples/` path also marks a project as a sample. A
  debug-key fallback used only when the keystore is missing is info.
- **review.sh.** `== RELEASE` runs after ACCESSIBILITY with `--no-release`
  and the `--skip` key `release`. It runs **whole-project even in diff mode**,
  and says so in a note. It has reviewer Template O.
- **Calibration.**
  - Canonical apps: compass_app, the bloc examples, the riverpod examples
    (`riverpod@87aad84`, re-cloned) and `news_toolkit/flutter_news_example`
    have zero high or medium hits.
  - Non-canonical apps: `io_flip`, immich, lichess, hiddify and wonderous.
  - About 120 CI workflows were scanned; the only hit was 1 low (immich: a
    keystore left on a persistent self-hosted runner).

---

# Phase 7 contracts (v1.4.0)

## 31. flutter-platform-integration

**Scope.** Talking to native code safely:
- **Channels:** `MethodChannel`, `EventChannel` and `BasicMessageChannel`,
  with channel names as one constant and codecs.
- **Pigeon:** typed channels, generated code kept out of review, and the
  `@HostApi`/`@FlutterApi` design.
- **FFI:** `dart:ffi`, `ffigen`, `jnigen`, native assets and build hooks, plus
  memory ownership (`calloc`/`free`, `using()` arenas, `Finalizable`) and long
  calls moved off the UI isolate.
- **Platform views** (`AndroidView`, `UiKitView`) and their performance cost.
- **Writing a plugin:** federated plugins, platform interfaces, and
  `implements` vs `extends`.
- **Permissions:** requesting them at the moment of use, and handling denied
  and permanently-denied states.
- **Background and isolate rules:** `BackgroundIsolateBinaryMessenger` and
  `RootIsolateToken`.
- **Errors:** `PlatformException`, `MissingPluginException`,
  `UnimplementedError` on unsupported platforms, and `kIsWeb` guards.
- **Testing:** `TestDefaultBinaryMessengerBinding` /
  `setMockMethodCallHandler` and fake platform interfaces.

**Architecture placement.** A platform channel or FFI binding is a **data
source**. It lives in `data/` (or a plugin package) behind a repository or
service contract. The repository maps `PlatformException` to a typed failure.
Views and logic (MVN notifiers, MVVM view models, blocs, GetX controllers)
never touch a channel or a native pointer. Permission requests are the one UI
exception: the view asks, the logic decides when, and a service wraps the
plugin.

**Contract values.**

| Item | Value |
|---|---|
| Owner | Agent P7: `skills/flutter-platform-integration/**` |
| Prefix | `PLAT-0xx` / `PLAT-<slug>` |
| Checker | `scripts/check_platform.py` (§22 CLI and output contract; Dart only, it may also read `pubspec.yaml` and `ffigen.yaml`/`pigeons/*.dart`) |
| Header | `== PLATFORM` |
| Schema | `flutter-pro-skills/platform@1` |
| Suppression | `plat-ignore` |

**Ownership.**
- arch_check doesn't treat channels as I/O. **PLAT owns platform-channel
  placement**: a `MethodChannel` or FFI call in a view, widget or logic file.
- Everything below stays with its owner. Cross-reference these; never
  re-detect them:

  | Concern | Owner |
  |---|---|
  | HTTP/DB I/O in UI | ARCH-005/101 |
  | Generic swallowed or untyped catches | ERR-001/002/003 |
  | Unguarded I/O in UI | ERR-014 (PLAT owns only the *channel-specific* missing `PlatformException`/`MissingPluginException` handling) |
  | Minimal permissions, secrets over channels | flutter-secure-defaults |
  | iOS usage descriptions | REL-009 |
  | Heavy work on the UI isolate | PERF-011 (PLAT owns *synchronous FFI calls* only) |
  | Undisposed controllers | UI-lifecycle (PLAT owns `EventChannel` stream subscriptions never cancelled only when channel-specific) |

**Secure by default.**
- Validate every value that comes back from native code at the source
  boundary.
- Never send tokens over a channel unless it's needed.
- Free every native allocation.
- Never load a dynamic library from a writable path.
- Request permissions only when they're used.

**Review integration (lead).**
- `== PLATFORM` runs after `== NETWORKING`, with `--no-platform` and the
  `--skip` key `platform`. It is informational.
- Add reviewer Template P and the dedupe rows.
- Bump to v1.4.0: nineteen skills, fifteen checkers.

**Calibration (§24).**
- **Canonical apps** (zero high or medium false positives):
  - compass_app, the bloc examples and the riverpod examples, which must stay
    quiet
  - the Flutter team's `samples/platform_channels`, `samples/add_to_app/**`
    (Pigeon), `samples/pedometer` (FFI/jnigen) and
    `samples/platform_view_swift` (all BSD)
- **Non-canonical apps:** immich/mobile (Pigeon, FFI; AGPL), lichess
  (channels; GPL) and hiddify (FFI; GPL). Their fixtures are fresh repros with
  no copied lines.

## 32. Phase 7 as built: v1.4.0 (these entries win over §31)

- **Release.** v1.4.0 has nineteen skills and fifteen checkers. Every
  `metadata.version` is `"1.4.0"`.
- **Rules.** `platform@1` has PLAT-001…012:
  - PLAT-001 channel-outside-data-layer (reported once per file; skips the
    composition root, wrapper classes, logic classes in core/data/domain, and
    `SystemChannels.*`)
  - PLAT-002 channel-name-duplicated
  - PLAT-003 platform-call-unhandled (callers followed up to 3 hops)
  - PLAT-004 platform-result-force-unwrapped
  - PLAT-005 event-subscription-dropped
  - PLAT-006 native-memory-not-freed
  - PLAT-007 library-loaded-from-writable-path
  - PLAT-008 call-handler-never-cleared
  - PLAT-009 platform-interface-not-enforced
  - PLAT-010 isolate-channel-without-messenger
  - PLAT-011 permission-requested-at-startup
  - PLAT-012 permanent-denial-unhandled

  There are also 8 reading slugs.
- **Generated code.** Generated Pigeon, ffigen and jnigen output is skipped,
  found both by its banner and by the configured output paths (`dartOut`,
  `ffigen.yaml`, pubspec `ffigen:`, `jnigen.yaml`).
- **Ownership** (as in §31, plus these):
  - PLAT-005 beats the `undisposed-resource` candidate only when the `listen`
    result is discarded. The deferral is a reviewer dedupe rule;
    `heuristics.py` doesn't defer by line.
  - PLAT-011 beats `SEC-permission-overreach` for the startup case.
  - Synchronous FFI work on the UI isolate is the reading slug
    `PLAT-sync-ffi-on-ui-isolate` (PERF-011 keeps Dart work).
- **review.sh.** `== PLATFORM` runs after NETWORKING, with `--no-platform`
  and the `--skip` key `platform`. Reviewer Template P covers it.
- **Scaffold.** The generated files get zero PLAT findings, enforced in
  tests.
- **Calibration.**
  - **Canonical apps:** compass_app, the bloc examples, the riverpod
    examples, and the Flutter samples `platform_channels`, `add_to_app/**`
    (Pigeon), `pedometer` (FFI/jnigen) and `platform_view_swift`. They have
    zero high or medium hits; every low was read and judged a true positive.
  - **Non-canonical apps:**
    - hiddify: 5 high PLAT-006 true positives (`toNativeUtf8()` passed inline
      and never freed)
    - immich, lichess, news_toolkit, io_flip, wonderous
    - a read-only robustness pass over 173 cached pub.dev plugin packages
