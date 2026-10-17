# Architecture anti-pattern catalog

Every rule the `flutter-architecture` skill reports: the import-graph rules
(`ARCH-0xx`) and code-pattern rules (`ARCH-1xx`) that `scripts/arch_check.py`
checks, and the judgment-only anti-patterns (`AP-*`) a reviewer finds by
reading. IDs, names and default severities match `docs/CONTRACTS.md` §6.

**Anti-patterns are profile-relative.** Each entry says where it applies and
where it doesn't. If the detected pattern is in the "doesn't apply" list, it
isn't a finding. Severity follows the suite scale: **High** = a bug now or a
violation that defeats the pattern's core guarantee; **Medium** = hurts
maintainability, testability or performance; **Low** = a local consistency fix;
**Info** = a trade-off, not a defect. Raise or lower one step when the evidence
justifies it, and say why.

Snippets are trimmed to the lines that matter; imports are shown when the
import is the point.

The catalog is split by group. This file is the index: read it first, then open
only the group file that holds the rule you need. Every entry keeps its
`### <ID> <name>` heading, so one grep finds it wherever it lives (see §3).

## Contents

1. Index (all IDs at a glance, with the file each entry lives in)
2. Groups (what each group file covers)
3. Finding an entry
4. Calibration notes (how arch_check grades, as built)

## 1. Index

| ID | Name | Default | Applies to | Detect | Entry |
|---|---|---|---|---|---|
| ARCH-001 | domain-depends-on-data | High | domain layer exists | import | [dependency-rule](anti-patterns/dependency-rule.md#arch-001-domain-depends-on-data) |
| ARCH-002 | domain-depends-on-presentation | High | domain layer exists | import | [dependency-rule](anti-patterns/dependency-rule.md#arch-002-domain-depends-on-presentation) |
| ARCH-003 | domain-depends-on-framework | Medium (`foundation.dart`: Low) | domain layer exists | import | [dependency-rule](anti-patterns/dependency-rule.md#arch-003-domain-depends-on-framework) |
| ARCH-004 | data-depends-on-presentation | High | all | import | [dependency-rule](anti-patterns/dependency-rule.md#arch-004-data-depends-on-presentation) |
| ARCH-005 | ui-depends-on-data-source | High | all | import | [presentation](anti-patterns/presentation.md#arch-005-ui-depends-on-data-source) |
| ARCH-006 | ui-depends-on-dto | Medium | clean_architecture, or `*_dto/_request/_response.dart` | import | [presentation](anti-patterns/presentation.md#arch-006-ui-depends-on-dto) |
| ARCH-007 | logic-depends-on-concrete-data | Medium | all | import | [data-and-repositories](anti-patterns/data-and-repositories.md#arch-007-logic-depends-on-concrete-data) |
| ARCH-008 | view-depends-on-repository | Medium | mvvm, mvn, bloc, mvc, getx | import | [presentation](anti-patterns/presentation.md#arch-008-view-depends-on-repository) |
| ARCH-009 | logic-depends-on-flutter-ui | Medium (getx: Low) | all | import | [presentation](anti-patterns/presentation.md#arch-009-logic-depends-on-flutter-ui) |
| ARCH-010 | sibling-logic-dependency | Medium bloc; Low mvvm/mvc/getx | not mvn, not riverpod | import | [pattern-specific](anti-patterns/pattern-specific.md#arch-010-sibling-logic-dependency) |
| ARCH-011 | repository-depends-on-repository | Medium | all | import | [data-and-repositories](anti-patterns/data-and-repositories.md#arch-011-repository-depends-on-repository) |
| ARCH-012 | mvn-notifier-bypasses-usecase | Medium | mvn only | import | [pattern-specific](anti-patterns/pattern-specific.md#arch-012-mvn-notifier-bypasses-usecase) |
| ARCH-013 | core-depends-on-feature | Medium | feature-first, hybrid | import | [dependency-rule](anti-patterns/dependency-rule.md#arch-013-core-depends-on-feature) |
| ARCH-014 | cross-feature-internal-import | Low | feature-first, hybrid | import | [dependency-rule](anti-patterns/dependency-rule.md#arch-014-cross-feature-internal-import) |
| ARCH-015 | feature-cycle | Medium | feature-first, hybrid | import | [dependency-rule](anti-patterns/dependency-rule.md#arch-015-feature-cycle) |
| ARCH-101 | io-in-widget | High | all | regex | [presentation](anti-patterns/presentation.md#arch-101-io-in-widget) |
| ARCH-102 | context-in-logic | Medium | all (getx: `Get.` navigation OK) | regex | [presentation](anti-patterns/presentation.md#arch-102-context-in-logic) |
| ARCH-103 | god-file | Medium | all | line count | [presentation](anti-patterns/presentation.md#arch-103-god-file) |
| ARCH-104 | service-locator-in-ui | Low | all except getx | regex | [di-and-globals](anti-patterns/di-and-globals.md#arch-104-service-locator-in-ui) |
| ARCH-105 | global-mutable-state | Medium | all | regex | [di-and-globals](anti-patterns/di-and-globals.md#arch-105-global-mutable-state) |
| ARCH-106 | mutable-state-class | Medium | mvn, bloc, riverpod, mvvm | regex | [state](anti-patterns/state.md#arch-106-mutable-state-class) |
| ARCH-107 | repository-leaks-transport | Medium | repository_pattern | regex | [data-and-repositories](anti-patterns/data-and-repositories.md#arch-107-repository-leaks-transport) |
| ARCH-108 | concrete-repository-only | Low | clean_architecture, mvn, mvvm | regex | [data-and-repositories](anti-patterns/data-and-repositories.md#arch-108-concrete-repository-only) |
| ARCH-109 | ephemeral-state-in-provider | Low | riverpod, mvn, provider | regex | [state](anti-patterns/state.md#arch-109-ephemeral-state-in-provider) |
| ARCH-110 | provider-init-from-widget | Low | riverpod, mvn | regex | [pattern-specific](anti-patterns/pattern-specific.md#arch-110-provider-init-from-widget) |
| ARCH-111 | event-flag-in-state | Low | mvn, bloc, mvvm, riverpod | regex | [state](anti-patterns/state.md#arch-111-event-flag-in-state) |
| ARCH-112 | mvn-forbidden-naming | Low | mvn only | regex | [pattern-specific](anti-patterns/pattern-specific.md#arch-112-mvn-forbidden-naming) |
| ARCH-113 | getx-in-build | Low | getx | regex | [pattern-specific](anti-patterns/pattern-specific.md#arch-113-getx-in-build) |
| AP-massive-view | logic in widgets ("smart UI") | High with I/O or rules; else Medium | all | reading | [presentation](anti-patterns/presentation.md#ap-massive-view) |
| AP-god-viewmodel | god view model / notifier / bloc | Medium | all | reading | [presentation](anti-patterns/presentation.md#ap-god-viewmodel) |
| AP-boolean-soup-state | contradictory flags | Medium | all | reading | [state](anti-patterns/state.md#ap-boolean-soup-state) |
| AP-null-as-loading | `null` means loading | Medium | all | reading | [state](anti-patterns/state.md#ap-null-as-loading) |
| AP-dto-as-ui-state | DTOs as UI state | Medium (small MVVM: Low) | all | reading | [state](anti-patterns/state.md#ap-dto-as-ui-state) |
| AP-leaky-repository | repository exposes transport | Medium | all | reading | [data-and-repositories](anti-patterns/data-and-repositories.md#ap-leaky-repository) |
| AP-two-sources-of-truth | duplicated, drifting state | High | all | reading | [state](anti-patterns/state.md#ap-two-sources-of-truth) |
| AP-passthrough-usecase | use case that only forwards | Info | not mvn | reading | [over-engineering](anti-patterns/over-engineering.md#ap-passthrough-usecase) |
| AP-premature-domain-layer | over-architected small app | Info | not when declared/mandated | reading | [over-engineering](anti-patterns/over-engineering.md#ap-premature-domain-layer) |
| AP-interface-for-everything | interface with one impl, no fake | Info | not mvn/clean contracts | reading | [over-engineering](anti-patterns/over-engineering.md#ap-interface-for-everything) |
| AP-exceptions-across-layers | transport errors escape | Medium | all | reading | [data-and-repositories](anti-patterns/data-and-repositories.md#ap-exceptions-across-layers) |
| AP-stream-subscription-in-widget | hand-managed subscriptions | High if never cancelled; else Medium | all | reading | [presentation](anti-patterns/presentation.md#ap-stream-subscription-in-widget) |
| AP-bloc-to-bloc | blocs coupled to blocs | Medium | bloc | reading | [pattern-specific](anti-patterns/pattern-specific.md#ap-bloc-to-bloc) |
| AP-singleton-abuse | global access to singletons | Medium | all | reading | [di-and-globals](anti-patterns/di-and-globals.md#ap-singleton-abuse) |
| AP-context-passed-down-to-data | `BuildContext` in data layer | High | all | reading | [dependency-rule](anti-patterns/dependency-rule.md#ap-context-passed-down-to-data) |
| AP-hardcoded-config-in-sources | URLs/keys/timeouts in code | Medium | all | reading | [data-and-repositories](anti-patterns/data-and-repositories.md#ap-hardcoded-config-in-sources) |
| AP-navigation-in-logic | navigation from logic classes | Medium | not getx | reading | [presentation](anti-patterns/presentation.md#ap-navigation-in-logic) |
| AP-shared-mutable-model | models mutated in place | Medium | all | reading | [state](anti-patterns/state.md#ap-shared-mutable-model) |
| AP-feature-envy-across-features | doing another feature's job | Low | feature-first, hybrid | reading | [dependency-rule](anti-patterns/dependency-rule.md#ap-feature-envy-across-features) |
| AP-anemic-vs-fat-entity | rules duplicated / entities doing I/O | Info | clean_architecture, mvn | reading | [over-engineering](anti-patterns/over-engineering.md#ap-anemic-vs-fat-entity) |
| AP-mvc-massive-controller | controller does everything | Medium | mvc, getx | reading | [pattern-specific](anti-patterns/pattern-specific.md#ap-mvc-massive-controller) |
| AP-getx-service-locator-everywhere | `Get.find` everywhere | Medium | getx | reading | [pattern-specific](anti-patterns/pattern-specific.md#ap-getx-service-locator-everywhere) |
| AP-riverpod-dynamic-providers | providers created at runtime | Medium | riverpod, mvn | reading | [pattern-specific](anti-patterns/pattern-specific.md#ap-riverpod-dynamic-providers) |
| AP-riverpod-side-effects-in-provider-build | writes in provider build | High | riverpod, mvn | reading | [pattern-specific](anti-patterns/pattern-specific.md#ap-riverpod-side-effects-in-provider-build) |
| AP-viewmodel-exposes-repository | public repository on logic class | Low | mvvm, bloc, mvc, getx | reading | [pattern-specific](anti-patterns/pattern-specific.md#ap-viewmodel-exposes-repository) |
| AP-mvn-legacy-riverpod-syntax | StateNotifier/ChangeNotifier in MVN | Low | mvn | reading | [pattern-specific](anti-patterns/pattern-specific.md#ap-mvn-legacy-riverpod-syntax) |
| AP-default-hides-missing-state | wildcard over a sealed state | Low | all | reading | [state](anti-patterns/state.md#ap-default-hides-missing-state) |
| AP-mixed-architecture | two patterns for one job | Medium (documented migration: Info) | all | reading | [pattern-specific](anti-patterns/pattern-specific.md#ap-mixed-architecture) |

The last four `AP-*` entries go beyond the minimum set in CONTRACTS §6.

## 2. Groups

**[Dependency rule](anti-patterns/dependency-rule.md)** (`references/anti-patterns/dependency-rule.md`). Import direction between layers and features: the domain importing data, presentation or Flutter; data importing presentation; `core/` importing a feature; one feature importing another's internals or forming a cycle; a feature doing another feature's job; and `BuildContext` handed down to data code.
IDs: ARCH-001, ARCH-002, ARCH-003, ARCH-004, ARCH-013, ARCH-014, ARCH-015, AP-feature-envy-across-features, AP-context-passed-down-to-data.

**[Presentation](anti-patterns/presentation.md)** (`references/anti-patterns/presentation.md`). Views and the logic classes behind them: views importing data sources, DTOs or repositories; logic classes importing Flutter UI or holding `BuildContext`; I/O in widgets; god files, massive views and god view models; navigation driven from logic; and stream subscriptions managed by hand in widgets.
IDs: ARCH-005, ARCH-006, ARCH-008, ARCH-009, ARCH-101, ARCH-102, ARCH-103, AP-massive-view, AP-god-viewmodel, AP-navigation-in-logic, AP-stream-subscription-in-widget.

**[State](anti-patterns/state.md)** (`references/anti-patterns/state.md`). Modelling and owning state: mutable state classes, ephemeral UI state kept in providers, one-time events stored as flags, contradictory booleans, `null` meaning loading, DTOs used as UI state, two sources of truth, models mutated in place, and `default`/wildcard branches that hide a missing case of a sealed state.
IDs: ARCH-106, ARCH-109, ARCH-111, AP-boolean-soup-state, AP-null-as-loading, AP-dto-as-ui-state, AP-two-sources-of-truth, AP-shared-mutable-model, AP-default-hides-missing-state.

**[Data and repositories](anti-patterns/data-and-repositories.md)** (`references/anti-patterns/data-and-repositories.md`). The data layer's contract: logic importing concrete repositories or services, repositories depending on repositories, repositories exposing transport types or letting transport exceptions escape, repositories with no contract to fake, and URLs, keys and timeouts hard-coded in sources.
IDs: ARCH-007, ARCH-011, ARCH-107, ARCH-108, AP-leaky-repository, AP-exceptions-across-layers, AP-hardcoded-config-in-sources.

**[DI and globals](anti-patterns/di-and-globals.md)** (`references/anti-patterns/di-and-globals.md`). Finding dependencies: service locators called from the UI, global mutable state, and singletons reached from everywhere instead of being injected.
IDs: ARCH-104, ARCH-105, AP-singleton-abuse.

**[Over-engineering](anti-patterns/over-engineering.md)** (`references/anti-patterns/over-engineering.md`). Info-level trade-offs rather than defects: pass-through use cases, a premature domain layer, an interface for every class, and anemic or fat entities. Report them only when the ceremony visibly costs the team, and never when the project or its pattern mandates the structure.
IDs: AP-passthrough-usecase, AP-premature-domain-layer, AP-interface-for-everything, AP-anemic-vs-fat-entity.

**[Pattern-specific](anti-patterns/pattern-specific.md)** (`references/anti-patterns/pattern-specific.md`). Rules owned by one pattern: sibling logic dependencies and bloc-to-bloc coupling (Bloc), notifiers bypassing use cases, forbidden names and legacy Riverpod syntax (MVN), providers initialised from widgets, created at runtime or writing in `build` (Riverpod), `Get.*` in `build` and `Get.find` everywhere (GetX), the massive MVC controller, a logic class exposing its repository, and two architectures for one job.
IDs: ARCH-010, AP-bloc-to-bloc, ARCH-012, ARCH-112, AP-mvn-legacy-riverpod-syntax, ARCH-110, AP-riverpod-dynamic-providers, AP-riverpod-side-effects-in-provider-build, ARCH-113, AP-getx-service-locator-everywhere, AP-mvc-massive-controller, AP-viewmodel-exposes-repository, AP-mixed-architecture.

## 3. Finding an entry

Grep for the heading across the references folder, then read from that line
to the next `### ` heading:

```bash
grep -rn '^### ARCH-005' references/
grep -rn '^### AP-god-viewmodel' references/anti-patterns/
```

Each entry gives the default severity, where it applies and where it doesn't,
how it is detected, then the problem, why it matters, bad and good code, the
fix and known false positives.

## 4. Calibration notes (how arch_check grades, as built)

Calibrated against compass_app, the bloclibrary and riverpod examples,
hiddify, lichess, insta, habo and an MVN control app. The entries in the group
files describe the anti-pattern; these notes say what the checker exempts or
grades down, so that a hit on a canonical app is worth reading.

- **ARCH-001**: a use case importing an abstract (or contract-less concrete)
  repository from `data/repositories/` is fine under mvvm (the Flutter guide
  keeps repositories in `data/`), and in any profile that has no
  `domain/repositories/` contract layer. DTOs, sources and implementations still
  fire.
- **ARCH-002**: medium (not high) when the imported presentation file declares
  no widget, for example a formatting helper under `ui/`.
- **ARCH-003** and **ARCH-009**: when Flutter UI libraries are imported only for
  value types (`Color`, `TimeOfDay`, `DateTimeRange`, `ThemeMode`, `Locale`,
  `Offset`, ...), the hit is low with "import foundation.dart or `show` the
  type" (ARCH-003 under mvvm only; MVN and Clean domains stay pure Dart). Under
  getx, ARCH-009 fires (low) only when widgets, `BuildContext`, navigation or
  dialogs are used; controllers, keys and `Color` are idiomatic there. The
  bloc accessor `static XCubit get(BuildContext c) => BlocProvider.of(c)` is one
  low ARCH-102 per file ("use context.read<X>() at call sites") and no ARCH-009.
- **ARCH-008**: building a view model from providers is a DI seam (every use of
  the repository sits inside a `*ViewModel(`/`create:` argument, e.g.
  `HomeViewModel(bookingRepository: context.read<BookingRepository>())`).
- **ARCH-010**: logic importing a barrel is judged by the logic files the
  barrel re-exports that the importer actually uses; its own barrel, state and
  events don't count.
- **ARCH-014**: under riverpod and mvn, importing another feature only to
  watch its providers is allowed. A bloclibrary feature's `models/` is its
  public API.
- **ARCH-101**: in the composition root only hits inside widget classes count
  (bootstrap I/O in `main()` is fine). `jsonDecode` counts only on a response
  or file body, or in a class that also does I/O. Top-level providers in a
  widget file are not the widget. SDK singletons (`Supabase.instance`,
  `FirebaseAuth.instance`, ...) and call shapes such as
  `widget.httpClient!.post(`, `_client.get(` and `Socket.connect(` count.
- **ARCH-102**: only inside logic class bodies (an `extension on BuildContext`
  in a notifier file doesn't count), and not in the composition root (routing
  helpers navigate by design).
- **ARCH-104**: also hand-rolled locators (`ServiceLocator.instance.x`,
  `*Locator.I`, `*Injector.get`) and project aliases of get_it
  (`final injector = GetIt.I;` then `injector<X>()`). Under bloc, a locator call
  inside `BlocProvider(create:)` is exempt (bloc.md section 7).
- **ARCH-105**: a top-level or static variable that nothing in `lib/`
  reassigns is low with "declare it final/const"; medium only when it is really
  reassigned. `static X? _instance` holders point to AP-singleton-abuse; a
  credential-like name holding a string literal points to
  flutter-secure-defaults (SEC-*).
- **ARCH-106**: content beats the file name, so a ChangeNotifier in a
  `*_state.dart` file is logic and not checked.
- **ARCH-107**: also SDK types returned by repositories that import the SDK
  (`User`, `UserCredential` from firebase_auth; `DocumentSnapshot`,
  `QuerySnapshot` from cloud_firestore; Supabase `AuthResponse`, ...), unless
  the project declares its own class of that name. A project record typedef
  named `*Response` is a domain value, not transport.
- **ARCH-110**: `ref.read` inside a callback that `initState` only registers
  (`addListener`, `listen`, `listenManual`, `subscribe`, `on*`) is fine;
  `addPostFrameCallback` and `Future.microtask` still count.
- **One report per import**: ARCH-005/008 and ARCH-007/012 on the same line
  are reported once, at the higher severity (ARCH-005 or ARCH-012 on a tie),
  with `also ARCH-0xx` in the note.
- **Not scanned**: `path:` packages (the profile lists them in `signals`; run
  the checker on each package) and generated files (see detect.md section 7).
  Vendored code copied under `lib/` is scanned; silence it with
  `// arch-ignore-file: ARCH-0xx vendored` in each file if you don't own it.
