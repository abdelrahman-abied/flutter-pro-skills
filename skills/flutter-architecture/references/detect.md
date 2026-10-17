# Detecting a Flutter app's architecture

Use this when `scripts/arch_check.py` can't run, when it reports `confidence:
low`, or when you want to check its call. It covers the same signals the script
uses (CONTRACTS §5), in the order a careful reader would check them.

## Contents

1. Start with what the project declares
2. Read the dependencies
3. Read the folder layout
4. Read the class names
5. The presentation decision table
6. The structural flags: clean architecture, repositories, use cases, layout
7. Classifying files into layers and roles
8. Mixed and migrating codebases
9. Reading the checker's output critically

## 1. Start with what the project declares

A declared architecture beats inference. Check, in order:

- your agent's project instructions file (`AGENTS.md`, `CLAUDE.md`,
  `GEMINI.md`, `.cursor/rules/…`, `.github/copilot-instructions.md`)
- `README.md` / `docs/` / ADRs ("we use MVVM", "Clean Architecture + Bloc")
- generator config: a `mason` brick, `get_cli` config, a VS Code extension
  config, `build.yaml` with `riverpod_generator`

If the project declares a pattern, pass it to the checker with
`--profile <value>` and judge against it, even if the code drifts. The drift is
the finding.

## 2. Read the dependencies

`pubspec.yaml` narrows the field quickly:

| Dependency | Suggests |
|---|---|
| `flutter_riverpod`, `hooks_riverpod`, `riverpod_annotation`, `riverpod_generator` | Riverpod; MVN if the MVN folders and naming are present (§3–4) |
| `flutter_bloc`, `bloc`, `hydrated_bloc` | Bloc / Cubit |
| `get` | GetX |
| `provider` | Provider + ChangeNotifier, often Flutter-team MVVM |
| `mvc_pattern`, `fluttery_framework`, `state_extended` | MVC |
| `stacked` | MVVM (stacked's `BaseViewModel`) |
| `get_it`, `injectable` | a service locator for DI. It says nothing about presentation |
| `freezed`, `equatable`, `built_value` | immutable models; any pattern |
| `dartz`, `fpdart`, `result_dart` | `Either`/`Result` error handling, common with Clean Architecture |
| none of the above | `setState`, or a hand-rolled `ChangeNotifier`/`ValueNotifier` setup |

Several of these together is normal: `flutter_bloc` + `get_it` + `freezed`, or
`provider` used only for DI under Riverpod-free MVVM. The dependency tells you
what is *available*; the folders and class names tell you what is *used*.

Also look for **local path packages** (`packages/`, `path:` dependencies). Bloc
tutorials and larger apps put the API client and repositories in separate
packages, so the layering is enforced by package boundaries. The checker only
scans `lib/` of the root package and sees those as external packages; read them
separately if they matter.

## 3. Read the folder layout

Typical shapes, from most to least specific:

```text
lib/features/<f>/{domain,data,presentation}/        Clean Architecture per feature
lib/features/<f>/presentation/{notifier,state,view,widget}/   MVN (singular folder names)
lib/ui/<f>/{view_model,widgets}/  lib/data/{repositories,services}/   Flutter MVVM (Compass app)
lib/<f>/{bloc,cubit,view}/  lib/<f>/<f>.dart barrel   Bloc tutorials
lib/app/modules/<m>/{bindings,controllers,views}/     GetX (get_cli)
lib/{models,views,controllers}/                       MVC
lib/{screens,widgets,services,models}/                setState or Provider, unlayered
```

`layout` in the profile is `feature-first` when `lib/features/` (or `modules/`,
`feature/`) holds two or more features, `layer-first` when `lib/` is split into
top-level `data/`, `domain/`, `presentation/`, `ui/`, `screens/`, `models/` or
`services/`, and `hybrid` when both. Layout is orthogonal to the pattern: MVVM
can be feature-first, Clean Architecture can be layer-first.

## 4. Read the class names

Count role suffixes across `lib/` (ignore generated files):

- `*Notifier` extending a generated `_$…` base (`class MovieNotifier extends
  _$MovieNotifier`) → Riverpod codegen notifiers; MVN if under `notifier/`
- `*ViewModel` → MVVM, whatever state library backs it
- `*Bloc`/`*Cubit`, `*Event`, `*State` → Bloc
- `extends GetxController`, `Obx(`, `GetView<` → GetX
- `extends ControllerMVC` / `StateMVC<` / `StateXController` / `StateX<` → MVC
  packages
- `*Controller` that is **not** GetX and **not** a Flutter controller
  (`TextEditingController`, `AnimationController`, `ScrollController`,
  `PageController`, `TabController`) → hand-rolled MVC
- `*Repository`, `*RepositoryImpl`, `*UseCase`/`*Usecase`, `*Service`,
  `*Source`/`*DataSource`, `*Dto`/`*Response`/`*Request`, `*Entity` → layering
  vocabulary, independent of the presentation pattern

Three or more classes with the same role suffix is a pattern; one is an accident.

## 5. The presentation decision table

Most specific wins. Record the evidence you used; it goes into the opening line
of your report.

| Value | Strong signals | Notes for a human reader |
|---|---|---|
| `mvn` | Riverpod dependency, no `view_model(s)/` folders, **and use cases** (the MVN spec makes them mandatory): `presentation/notifier(s)/` + use cases is **high**; use cases + ≥3 `*Notifier extends _$X` is **medium**; `presentation/notifier/` + `domain/` but 0 use cases is **low** | ≥3 codegen `*Notifier` classes without `domain/usecases/` is plain Riverpod naming, not MVN (signal: "plain Riverpod naming, not MVN"). MVN also bans `controller`/`viewmodel` naming, so finding those in an "MVN" app is either drift or a different pattern. `application/` services (codewithandrea) are not MVN use cases |
| `mvvm` | `view_model(s)/` or `viewmodel(s)/` folders, or ≥3 `*ViewModel` classes | Any backing library counts: ChangeNotifier, Provider, Riverpod, stacked. Riverpod + `*ViewModel` is MVVM, not MVN |
| `bloc` | `bloc`/`flutter_bloc` dependency, or `*_bloc.dart`/`*_cubit.dart` files | Cubit-only apps are still `bloc` |
| `getx` | `get` dependency and `GetxController` subclasses | GetX is MVC-flavoured but has its own rules (service locator, `Obx`) |
| `mvc` | `mvc_pattern`/`fluttery_framework` dependency, or `controller(s)/` folders with `*Controller` classes that aren't GetX or Flutter controllers, plus `model(s)/` + `view(s)/` | Flutter has no official MVC guidance; see `mvc.md` |
| `provider` | `provider` dependency, `ChangeNotifier` models, no view-model naming | Often MVVM in all but name; judge with `mvvm.md`'s rules at reduced strength |
| `riverpod` | Riverpod dependency without the MVN folders or naming | Judge with riverpod.dev's DO/DON'T (`state-management.md`) |
| `setstate` | no state-management dependency, mostly `StatefulWidget` + `setState` | Fine for small apps. Flag only real harm |
| `unknown` | nothing conclusive | Read two features end to end and describe what you see instead of forcing a label |

**Majority wins between getx, mvvm and bloc.** The checker counts
GetxController subclasses, view models and blocs/cubits and picks the largest
group. A minority pattern never decides the label (one `GetxController` in a
21-cubit app is still `bloc`). Instead it adds the signal `mixed architecture:
… report AP-mixed-architecture once` and caps confidence at medium. Report it
once, as in section 8.

Every profile also carries `use cases: N files`, and `path packages: a, b (not
scanned)` when pubspec has `path:` dependencies (bloclibrary keeps its
repositories in `packages/*_repository`; a path or imported package named
`*_repository` sets `repository_pattern: true`). Path packages are **not**
scanned: run the checker on each package root to review them.

## 6. The structural flags

These are independent of `presentation` and change which rules apply.

- **`clean_architecture: true`**: `domain/` and `data/` directories exist (top
  level or per feature) **plus** at least one of `usecases/`, `use_cases/` or
  `entities/`. Caution: the Flutter team's own Compass app has
  `lib/domain/{models,use_cases}` and `lib/data/`, so a Flutter-MVVM app with
  the optional domain layer also gets `true`. **`mvvm` + `clean_architecture`
  does not make use cases mandatory.** The Flutter guide lets view models use
  repositories and use cases side by side.
- **`repository_pattern: true`**: there are `*Repository` types. Enables
  ARCH-107 (repository leaks transport types).
- **`use_cases: true`**: there are use-case classes or folders. Under MVN and
  strict Clean Architecture they are the only door from logic to data; under
  MVVM and Bloc they are optional helpers.
- **`layout`**: feature-first and hybrid layouts enable the cross-feature rules
  ARCH-013/014/015.
- **`state_management`** and **`di`** list what's in use, e.g. `["riverpod"]`
  and `["riverpod", "get_it"]`. Two DI mechanisms in one app is worth one Info
  finding; two state-management libraries for the same job is worth one Medium.

## 7. Classifying files into layers and roles

When you read by hand, classify each file the way the checker does, so your
findings line up with its IDs.

**Layer**: the first match among the path segments (case-insensitive):

A leading `lib/src/` is stripped first (package layout), so `lib/src/model/x.dart`
is classified like `lib/model/x.dart`. Dotted file names are read by their
suffix: `x.repository.dart` is `x_repository`.

| Layer | Path segments |
|---|---|
| domain | `domain` |
| data | `data`; also the weaker layer-first folders `models`, `model`, `services`, `repositories`, `api`, `datasources` (logic and UI found there keep their role, with layer `other`) |
| presentation | `presentation`, `ui`, `view`, `views`, `screens`, `pages`, `widgets` |
| core | `core`, `shared`, `common`, `utils`; also logger/analytics/crash/telemetry services |
| composition root | `lib/main*.dart`, `lib/app.dart`, `lib/bootstrap.dart`, files directly in `lib/app/` (not its subfolders), `lib/config/**` (Flutter MVVM's `config/dependencies.dart`), and `di/`, `injection/`, `router/`, `routes/`, `routing/`, `bindings/` folders. Routing glue (`RouterDelegate`, `RouteInformationParser`/`Provider`, `*RefreshStream`/`*RefreshListenable` adapters) is composition root too. It may import anything |

**Features**: the segment after `features/`, `feature/` or `modules/`, and also
the bloclibrary layout, a top-level `lib/<feature>/` holding `bloc/`, `cubit/`,
`view/` or `widgets/`. Such a feature's `models/` (formz inputs, UI enums) is
presentation, role `other`, and other features may import it (it is the
feature's public API).

**Role**, from content first, then folder or suffix:

- `barrel`: only `import`/`export`/`part`/`library` directives. No rule applies
  to it; logic importing a barrel is judged by the logic files the barrel
  re-exports and the importer actually uses.
- `di`: DI wiring. Either a file whose top-level declarations are only providers
  that build objects (no Future/Stream providers, no `*Repository` class), or
  `*Factory`/`*Module`/`*Locator`/`*Injector` classes that only construct
  objects. Treated like the composition root.
- `logic` by content, in every profile: a class extending or mixing in
  `ChangeNotifier`/`ValueNotifier` (not a `*Repository` or `Command*`, not
  routing glue), a classic or codegen Riverpod notifier (`StateNotifier`,
  `Notifier`, `AsyncNotifier`, `extends _$X` with `@riverpod`), a Cubit/Bloc, or a
  GetX controller. Content beats the file name (`*_state.dart` holding a
  ChangeNotifier is logic) and the weak layer-first folders (`models/CartModel`).
  A file that also declares a `*Client`/`*Source`/`*Api`/`*Repository` class stays
  a data file. A file with only Widget/State classes is a `widget`/`view` even
  if it's named `*_controller.dart`.
- `repository` vs `repository-impl`: a concrete `*Repository` is an
  implementation only when a contract exists (it implements/extends an abstract
  `*Repository`, or `XRepositoryImpl` has an abstract `XRepository`). Otherwise it
  is `repository`: a concrete repository with no contract, normal in Bloc and
  Flutter MVVM. ARCH-007 skips it; a view depending on it is ARCH-008 (medium,
  with the BlocProvider exemption), not ARCH-005. Implementations are also found
  in `repositories_impl/`, `repository_impl/`, `repos/`, `*_repo_impl.dart`,
  `*_repo.dart`, or by `class XRepoImpl` / `implements XRepository`.

Then: `entity`, `repository-contract`
(`domain/repositories/`, or an abstract/interface repository), `usecase` (also
codewithandrea `application/` services), `dto`
(`data/models/`, `*_dto.dart`, `*_request.dart`, `*_response.dart`), `source`
(`sources/`, `datasources/`, `api/`, `remote/`, `local/`, `*_source.dart`,
`*_api.dart`, `*_client.dart`), `service` (`services/`, `*_service.dart`),
`logic` (`notifier/`, `view_model/`, `bloc/`, `cubit/`, `controller/` and the
matching suffixes, plus `_store`), `state` (`state/`, `*_state.dart`), `view`
(`views/`, `screens/`, `pages/`, `*_screen.dart`, `*_page.dart`, `*_view.dart`),
`widget` (other presentation files), and `event` (`*_event(s).dart` under or
next to `bloc/`/`cubit/`, or a `part of` a bloc; elsewhere it is not an event).
A content fallback sets the role but never the layer.

**I/O packages** (a widget or logic class importing these is reaching past the
data layer): `dio`, `http`, `retrofit`, `chopper`, `graphql`,
`graphql_flutter`, `sqflite`, `drift`, `hive`, `hive_flutter`, `isar`,
`objectbox`, `shared_preferences`, `flutter_secure_storage`, `cloud_firestore`,
`firebase_database`, `firebase_storage`, `firebase_auth`, `supabase_flutter`,
`supabase`, `web_socket_channel`, `grpc`, `path_provider`, `get_storage`,
`hive_ce`, `hive_ce_flutter`, `sembast`, `realm`, `floor`, `isar_community`.

**Generated files are skipped** and never appear in `files[]`: `*.g.dart`,
`*.freezed.dart`, `*.gr.dart`, `*.mocks.dart`, `*.config.dart`, `*.gen.dart`,
protobuf and chopper output, `lib/generated/`, `app_localizations*`/`messages_*`,
the `l10n.yaml` `output-dir`, or without one `<arb-dir>/<output-localization-file
stem>*.dart` (gen-l10n writes into arb-dir, default `lib/l10n`), and any file whose
header comment says `GENERATED CODE - DO NOT MODIFY`, `AUTO GENERATED`,
`DO NOT EDIT` or `Generated by`. `files[]` is the source of truth for scope:
other checkers should take it from there.

Watch for layouts that confuse segment matching. A get_cli project nests
everything under `lib/app/`, so only files *directly* in `lib/app/` count as the
composition root. `lib/app/modules/<m>/controllers|views|bindings/` are
classified by their role folder, and `modules/<m>` counts as a feature. If the
profile still puts many files in `app` or `other`, the import rules have little
to check there, so read those files yourself instead of trusting a clean report.

**What counts as "depending on" a file.** For the rules about sources, services,
repositories and use cases (ARCH-005/007/008/011/012), the checker only counts
an import when the importer uses a *primary* symbol of the target. That means a
repository/source/service/use-case class, a contract, a class with async
methods, or a provider. Importing a file just for its enum, exception or value
type is not a layering violation. A provider counts only when its value is a
primary type (`Provider<XRepository>`, `@riverpod XRepository x(Ref)`, a name
ending in `RepositoryProvider`/`ServiceProvider`/`ClientProvider`/...);
`FutureProvider`, `StreamProvider`, `AsyncNotifierProvider` and `@riverpod
Future<T>` providers declared next to a repository are neutral. An `abstract
class` with only static members is a namespace, not a contract. For I/O packages
the checker looks at *how* the importer uses the package: in a view only uses
inside Widget/State bodies count (a provider declared in the same file is logic);
exception types only (`is DioException`) are low ("transport exception reaches
the UI"); `CancelToken`, `Timestamp` and similar values don't count; transport
that is only constructed inside a `create:` argument or a `*Bloc(`/`*ViewModel(`
constructor call is low ("constructed at a DI site; see ARCH-007"). Bloc
events (`*_event(s).dart`) have their own `event` role, so a bloc importing its
events is not a sibling-logic dependency.

## 8. Mixed and migrating codebases

Real apps are often half-way between patterns: an old `provider` +
`ChangeNotifier` section, a newer Riverpod section, one feature someone
rewrote in Bloc.

1. **Classify per feature**, not per app. Note which features follow which
   pattern ("`auth`, `profile`: MVVM with Provider; `catalog`, `cart`: MVN").
2. **Judge each feature by its own pattern.** The Notifier in `catalog/` is
   held to MVN's rules; the view model in `auth/` to MVVM's. If the checker
   ran with a single profile, re-check pattern-specific hits (ARCH-010, 012,
   112) against the feature's real pattern and drop the ones that don't apply.
3. **Report the inconsistency once**, as a single finding, not once per file:
   ```markdown
   ### [MEDIUM] Two presentation patterns in one app
   - id: AP-mixed-architecture
   - where: lib/features/auth/, lib/features/profile/ (MVVM) vs lib/features/catalog/, lib/features/cart/ (MVN)
   - evidence: `*ViewModel extends ChangeNotifier` in 2 features; `@riverpod class *Notifier` in 5
   - rule: be consistent (precedence rule 1: the project's own conventions)
   - why: two vocabularies, two DI mechanisms and two test styles for the same job
   - fix: |
       Pick the target pattern (likely MVN, the majority), record it in the project
       instructions file, and migrate the MVVM features when they're next touched.
   - confidence: confirmed
   ```
   Use Info instead of Medium when the project documents an ongoing migration.
4. **When writing code** in a mixed app, follow the pattern of the feature you
   are in, or the declared target pattern for new features. Don't add a third.

## 9. Reading the checker's output critically

- `signals` lists the evidence. If it shows one weak signal (a `provider`
  dependency and nothing else), treat the label as a guess.
- A suspiciously clean report on a large app usually means files weren't
  classified (unusual folder names, everything under `lib/app/`, layering in
  path packages). Check `stats.by_layer` (the `files:` line in text mode): if most files are `other` or `app`,
  read the code.
- `suppressed` contains hits the project silenced and the MVN DI-seam
  exemption (ARCH-001 for a `@riverpod` use-case provider importing the
  repository implementation). Don't re-report them.
- **One report per import.** When ARCH-005 and ARCH-008, or ARCH-007 and
  ARCH-012, fire on the same import line, only the higher-severity (on a tie, the
  more specific: ARCH-005, ARCH-012) is kept, and its `note` says `also ARCH-0xx`.
- **Reusing the JSON.** `arch_check.py <root> --json > file` is the contract for
  reuse: the file is the complete `arch-profile@1` document, so a caller can run
  the checker once and hand the file to other checkers (the review skill exports
  it as `FPS_ARCH_JSON=<path>`). There is no separate write flag.
- The checker can't see runtime wiring (a `get_it` registration that binds a
  concrete type, a `Provider` override in tests). Read the composition root
  for DI questions.
