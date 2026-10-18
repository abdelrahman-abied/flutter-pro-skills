---
name: flutter-feature-scaffold
description: Scaffold a new Flutter feature, screen, page or module in the architecture the project already uses - MVN (Riverpod codegen notifiers + use cases), MVVM (view models with Command/Result), Bloc, Cubit, GetX, Provider or plain Riverpod. It detects the pattern, copies the project's conventions (feature-first vs layer-first, Screen/Page/View, import style), dry-runs first and never overwrites, and its output is secure by default, with fake-based tests. Use it first, before writing any files, whenever someone asks to create, add, build, scaffold or generate a feature, module, page or new screen (settings, profile, checkout), says "generate the boilerplate" or "set up a feature in clean architecture/MVN/MVVM/bloc", or wants a new repository, notifier, bloc, cubit or view model with its layers, even if they never say "scaffold". For restructuring existing code, use flutter-architecture.
license: MIT
metadata:
  author: abdelrahman-abied
  version: "1.6.0"
  suite: flutter-pro-skills
---

# Flutter feature scaffold

Creates a new feature, with every layer, in **the architecture the project
already uses**, not the one you'd pick for a fresh app. It runs the
`flutter-architecture` checker, copies the conventions it finds, and produces
code that passes that checker with zero violations for the profile. It also
writes test skeletons that use fakes, and prints the commands that make the
code compile. Every generated file is idiomatic Dart 3: sealed states,
`final class` data types, `abstract interface class` contracts, const
constructors and `super.key`. It is also **secure by default** (see below):
the code passes the suite's security, error-handling and forms checkers with
zero findings, so it needs no hardening pass afterwards.

The script is `scripts/scaffold.py` (Python ≥3.8, stdlib only). It is the only
script in the suite that writes into a project, and it does so only with
`--write`. It never overwrites a file, never edits `pubspec.yaml`, and never runs
pub, build_runner or the analyzer itself.

## Workflow

1. **Detect.** Check for a declared architecture first, because it beats
   inference: your agent's project instructions file (`AGENTS.md`, `CLAUDE.md`,
   `GEMINI.md`, `.cursor/rules/…`, `.github/copilot-instructions.md`), the README
   or ADRs. If one is declared, pass it as `--profile`. Otherwise `auto` runs
   `../flutter-architecture/scripts/arch_check.py --json` for you. In a mixed
   codebase, follow the pattern of the feature's neighbours or the declared
   target, and don't add a third (flutter-architecture › `detect.md` §8).
2. **Dry run** (the default) and read the plan:
   ```bash
   python3 -I <skill-dir>/scripts/scaffold.py <project-root> <feature_name> [--profile auto] [--clean] [--entity Name]
   ```
   `== SCAFFOLD PLAN` shows the pattern and why it was chosen, the layout and
   every inferred convention with its evidence. `== FILES` lists each file
   with the classes and providers it declares (`+` new, `=` exists and will be
   skipped). `== DEPENDENCIES` lists what's missing from pubspec.
3. **Confirm the plan with the user** before writing. Cover the feature name
   (snake_case, named for the user-facing capability: `order_history`, not
   `orders_screen`), the domain object name (`--entity Order` when it differs
   from the feature), and whether to add use cases (`--clean`). If confidence
   is `low` or the pattern looks wrong, ask, then re-run with `--profile`.
4. **Write**: add `--write`. Existing files are listed as `skipped … (exists, not
   overwritten)`. If the feature folder already exists the script stops (exit 2)
   unless you pass `--force-dir`, which adds only the missing files.
5. **Run the printed commands**, in order: `flutter pub add …` for missing
   dependencies, `dart run build_runner build -d` for MVN and Riverpod (the
   `*.g.dart` parts don't exist until then), then `dart analyze <paths>` and
   `flutter test <paths>`. Expect zero analyzer errors or warnings and green
   tests, because the templates are compile-checked against real projects.
6. **Wire it up** with the snippet under `== NEXT STEPS`: a route, plus
   `ProviderScope`, `RepositoryProvider`, `ChangeNotifierProvider` or a `GetPage`
   binding at the composition root, and the shared HTTP client created once
   there (`createHttpClient()`, or `Get.put(ApiClient())` for GetX).
7. **Fill in the TODOs.** The script prints the count. They mark the parts only
   you can write: the real fields of the entity, model and DTO (keep the
   `fromJson` shape check); the endpoint path in the source; the https base URL
   and the auth interceptor in the shared HTTP client; extra failure mapping in
   the repository; and localized, user-facing error text. The wording follows
   `flutter-secure-defaults` › `secure-scaffold-checklist.md` §10, so filling
   them in keeps the defaults.
8. Optionally re-run `arch_check.py` (or the `dart-flutter-review` skill) to
   confirm the feature still has zero violations after your edits.

Exit codes: `0` means the plan was printed or the files were written. `2` means
a usage or environment error: no pubspec, an invalid name, an unsupported or
undetectable pattern, or a feature that already exists.

## CLI

```text
python3 -I scripts/scaffold.py <project-root> <feature_name>
    [--profile auto|mvn|mvvm|bloc|cubit|getx|provider|riverpod]
    [--clean]            add domain/ entities + use cases where the pattern lacks them
    [--entity <Name>]    UpperCamel domain object name (default: from the feature)
    [--write]            create the files (never overwrites)
    [--force-dir]        allow adding files to an existing feature folder
```

Feature names must be snake_case (`order_history` → `OrderHistory`). Dart
keywords and names that would collide with core types (`state`, `error`,
`widget`, `test`) are rejected with a suggestion.

## What each profile generates

Every profile also gets two **app-wide files**, created once and reused (never
overwritten) by later features: `lib/core/error/failure.dart` (a sealed
`Failure` with `NetworkFailure`, `ServerFailure` and `ParseFailure`) and
`lib/core/network/http_client.dart`, the one configured Dio
(`createHttpClient()`, `failureFromDio()`, plus `httpClientProvider` for MVN
and Riverpod). GetX gets `core/network/api_client.dart` instead: `ApiClient
extends GetConnect` and `failureFromResponse()`. Both sit under `lib/app/core/`
in a get_cli app.

Paths are for a feature-first project (`lib/features/<f>/…`) with the pattern's
canonical folders. In a layer-first project the same files go to
`lib/{domain,data}/<folder>/…` and `lib/<presentation|ui>/<f>/<folder>/…`
(MVVM follows the Compass app: `lib/ui/<f>/…`, `lib/data/repositories/<f>/…`).
Every row marked † also gets `test/<same path>_test.dart`.

**MVN** follows the `mvn` spec's tree and golden template exactly, with singular
folders, the use-case-provider DI seam, a sealed state and `@riverpod`. If the
`mvn` skill (`mvn-architect:mvn`) is installed, it is the specialised
alternative for MVN-only work. `--clean` changes nothing here, because MVN is
already Clean.

| File | Declares |
|---|---|
| `domain/entities/<f>_entity.dart` | `XEntity` (`@immutable`) |
| `domain/repositories/<f>_repository.dart` | `abstract interface class XRepository` |
| `domain/usecases/<f>_usecase.dart` † | `FetchXList` + `fetchXListProvider` (the DI seam) |
| `data/models/<f>_request.dart`, `<f>_response.dart` | DTOs; `XResponse.toEntity()` |
| `data/repositories/<f>_repository_impl.dart` † | `XRepositoryImpl` + `xRepositoryProvider` |
| `data/sources/<f>_source.dart` | `XSource`, `XRemoteSource` + `xSourceProvider` |
| `presentation/notifier/<f>_notifier.dart` † | `XNotifier extends _$XNotifier` |
| `presentation/state/<f>_state.dart` | sealed `XState`: `XInitial/XLoading/XSuccess/XError` |
| `presentation/view/<f>_view.dart` † | `XView` (`ConsumerWidget`, exhaustive `switch`, `ref.listen`) |
| `presentation/widget/<f>_widget.dart` | `XWidget` (rename it descriptively as the UI grows) |

The provider name for `XNotifier` follows riverpod_generator: `xProvider` on
≥3.0 (it strips `Notifier`), `xNotifierProvider` on 2.x. The script reads
`pubspec.lock`/`pubspec.yaml` to decide. On Riverpod 3 it also adds
`if (!ref.mounted) return;` after the await in the notifier.

**MVVM** (Flutter architecture guide / Compass): a view model calls the
repository directly. `--clean` adds a Compass-style `XLoadUseCase` and moves
the contract to `domain/`.

| File | Declares |
|---|---|
| `domain/models/<x>.dart` | `X` (plain-noun domain model, value equality) |
| `data/services/<f>_api_client.dart`, `…/model/<f>_api_model.dart` | `XApiClient` (stateless, takes the injected `Dio`, maps errors to `Result.error(Failure)`), `XApiModel` |
| `data/repositories/<f>_repository.dart` | `abstract interface class XRepository` |
| `data/repositories/<f>_repository_remote.dart` † | `XRepositoryRemote` |
| `ui/view_models/<f>_viewmodel.dart` † | `XViewModel extends ChangeNotifier` with `late final Command0<void> load` |
| `ui/widgets/<f>_screen.dart` †, `<f>_list.dart` | `XScreen(viewModel:)` with `ListenableBuilder`; `XList` |
| `lib/utils/result.dart`, `lib/utils/command.dart` | Created only if the project has no Compass-shaped `Result`/`Command0` |

**Bloc / Cubit** (bloclibrary.dev): `bloc/<f>_bloc.dart` † with `part`
files `<f>_event.dart` (past-tense `XStarted`, `XRefreshRequested`) and
`<f>_state.dart` (sealed, Equatable: `XInitial/XLoadInProgress/XLoadSuccess/XLoadFailure`).
A cubit gets `cubit/<f>_cubit.dart` † with an imperative `load()`.
`view/<f>_page.dart` † holds `XPage` (provides the bloc with `BlocProvider`)
and `XView` (`BlocBuilder`), plus `widgets/<f>_list.dart`. The data layer is
`data/models/<x>.dart`, `data/data_providers/<f>_api.dart` (`XApi` +
`RemoteXApi`), and `data/repositories/` with the contract and `XRepositoryImpl` †.
Tests use `blocTest` with a fake repository.

**GetX** (get_cli): `lib/app/modules/<f>/bindings/<f>_binding.dart`,
`controllers/<f>_controller.dart` † (`XController extends GetxController`, an
`Rx<XState>`), `controllers/<f>_state.dart`, `views/<f>_view.dart`
(`GetView` + `Obx`) and `widgets/<f>_list.dart`. Data goes to `lib/app/data/`:
the model, `providers/<f>_provider.dart` (`XProvider` + `XApiProvider`, which
receives the shared `ApiClient`), and the repository contract and impl †.

**Provider** (ChangeNotifier): `presentation/notifiers/<f>_notifier.dart` †
(`XNotifier extends ChangeNotifier`, exposing a sealed `XState`),
`presentation/state/<f>_state.dart`, `presentation/screens/<f>_screen.dart` †
(`context.watch`) and `widgets/<f>_list.dart`. Data: the model,
`data/services/<f>_service.dart`, and the repository contract and impl †.

**Riverpod** (non-MVN, codegen): `presentation/providers/<f>_notifier.dart` †
(`@riverpod` `AsyncNotifier`, so `AsyncValue` models loading and error),
`presentation/screens/<f>_screen.dart` † and `widgets/<f>_list.dart`. The
feature's composition root is `di/<f>_providers.dart`, which binds the source
and the repository (and the use case) to their contracts, so the notifier
never imports an implementation. Data: the model, `data/sources/<f>_source.dart`,
and the repository contract and impl †.

**`--clean`** (Bloc, Cubit, GetX, Provider, Riverpod) replaces that data
layer with Clean Architecture: `domain/entities/<x>_entity.dart`,
`domain/repositories/`, `domain/usecases/fetch_<f>_list.dart` † (`FetchXList`
with `call()`), `data/models/<f>_dto.dart` (`toEntity()`),
`data/datasources/<f>_remote_data_source.dart` and `XRepositoryImpl` †. The
logic class then depends on the use case. It is switched on automatically when
the project already has `clean_architecture: true`.

## Secure by default

The templates follow the secure scaffold checklist, rules S-1 to S-33
(`../flutter-secure-defaults/references/secure-scaffold-checklist.md`), for
every profile, with and without `--clean`. Every generated feature guarantees:

- **One configured client, injected.** The source receives the app's HTTP
  client (Dio, or GetConnect for GetX) through its constructor or provider. It
  never builds `Dio()` or sets `BaseOptions`, so it can't skip the timeouts or
  the auth interceptor. Paths are relative (`'/orders'`); the https base URL and
  the timeouts live in the shared client (S-5, S-9, S-27, S-28).
- **No auth in features.** Nothing outside the shared client touches headers.
  The auth interceptor is a TODO there, because the scheme is app-specific (S-6).
- **Validated JSON.** `fromJson(Object? json)` pattern-matches the shape and
  throws `FormatException` on a mismatch. There are no `as` casts over
  untrusted JSON, and the source checks that the payload is a list (S-14).
- **Typed failures.** The repository maps transport errors
  (`DioException`, a GetConnect error response, `FormatException`) to a
  `Failure` that carries no URL, headers or server text. MVVM returns it in a
  `Result` (S-11).
- **User-safe errors.** Error state holds the `Failure`, never `e.toString()`.
  The view maps it to fixed text in one `_failureMessage` function, ready for
  localization, with a retry action (S-18, S-21, S-22, S-24).
- **Nothing logged.** No `print`, no logger and no HTTP logging interceptor.
  The shared client says where debug-only logging may go (S-1, S-8, S-10, S-29).
- **Nothing risky by default.** No certificate overrides, `String.fromEnvironment`,
  `http://` URLs, secrets, storage, WebViews, `launchUrl` or `HydratedBloc`
  (S-2, S-4, S-13, S-20, S-26, S-30). Tests use obviously fake data and
  check that a transport error becomes a typed failure (S-32, S-33).

The skill's tests enforce this: each profile and layout passes
`check_secure_defaults.py`, `check_errors.py` (nothing in the generated files),
`check_forms.py` and `arch_check.py` with zero findings, the generated files
get zero findings from `check_performance.py`, `check_persistence.py`,
`check_networking.py`, `check_firebase.py`, `check_platform.py`, `check_design_system.py`, `check_adaptive.py` and `check_accessibility.py` (clean by default: lazy
lists, theme colours, labelled buttons), plus greps for the
checklist rules the checkers can't see. If the project already configures a
client or declares a `Failure` type, the plan prints a `note:`. Inject that
client instead, so there's never a second, unauthenticated one (S-31).

## How conventions are inferred

Precedence rule 1 applies: the project's consistent conventions beat each
pattern's canonical layout, and the canonical layout is only the fallback. The
script reads the checker's per-file `files` array (layer, role, feature,
classes), or does its own minimal scan if the array or the checker is missing,
and takes the **majority** among existing files:

| Convention | Evidence | Fallback |
|---|---|---|
| Layout and feature root | profile `layout`; the folder that holds existing features (`lib/features`, `lib/modules`, `lib/app/modules`) | per pattern (MVVM layer-first, GetX `lib/app/modules`, others `lib/features`) |
| Presentation folder | `presentation/` vs `ui/` vs none, in existing features | per pattern |
| Folder names | parent folder of each role: `notifier/` vs `notifiers/`, `view/`, `views/`, `screens/`, `pages/`, `widget(s)/`, `sources/` vs `datasources/`, `usecases/` vs `use_cases/` | the pattern reference |
| View suffix | `_screen`/`_page`/`_view` file stems of view files | MVN/GetX `View`, Bloc `Page`, others `Screen` |
| Repository impl | `_repository_impl` vs `_repository_remote` | MVVM `Remote`, others `Impl` |
| Logic suffix (Provider, Riverpod only) | `Notifier`/`Controller`/`Store` classes | `Notifier` |
| Entity suffix | existing entity classes with or without `Entity` | MVN and `--clean`: `Entity` |
| Imports | count of `package:<own>/` vs relative own imports | relative (tests always use `package:`) |
| Constructor style | SDK lower bound ≥3.12 → `X({required this._dep})` | classic initializer list |

A pattern's fixed vocabulary is never "inferred away": MVN stays `Notifier`,
Bloc stays past-tense events, MVVM stays `ViewModel`. Only folder spelling, the
screen suffix and the other items above follow the project. Every inference is
printed with its evidence, so you can challenge it.

## What it deliberately does not generate

- **Auth and app config.** No login, token storage or interceptor, and no real
  base URL. The shared client has an https placeholder and a TODO for the auth
  interceptor (`../flutter-secure-defaults/references/secure-defaults-by-layer.md` has
  the code per pattern). Sources make a real call through the injected client, so
  the screen shows the error state until the base URL is set. The tests use
  fakes and pass at once.
- **Routing and app-level DI.** It prints the snippet, because routers
  (go_router, auto_route, get_cli pages) and root providers are shared files it
  won't edit. It also never edits `main.dart`, barrels or `pubspec.yaml`.
- **Generated code.** No `*.g.dart`, `freezed` or `json_serializable` output: run
  build_runner. Models use hand-written `fromJson` and `==`. Swap in
  freezed/equatable if the project uses them.
- **Speculative layers.** No use cases unless the pattern or `--clean` calls for
  them, no request DTO outside MVN, no mocks (tests use fakes that implement the
  contract), and no shared `UseCase<T, P>` base class.
- **Patterns it can't faithfully produce**: MVC and setState-only apps
  (`--profile` is required; describe the target to the user instead), or
  path-package data layers like the Bloc tutorials'.

## Notes

- A plain-Riverpod app with three or more `*Notifier extends _$X` classes looks
  like MVN to the checker. Declare `riverpod` in the project instructions file
  and pass `--profile riverpod`.
- Projects on `package:http` instead of Dio get a `note:`. The templates inject
  Dio, so swap the client type in the source and the shared client.
- GetX, Bloc and Provider versions differ in small APIs. The templates target
  current stable releases (flutter_bloc 9, get 4.7, provider 6, Riverpod 3).
  On Riverpod 2.x, regenerate with the 2.x generator and check the provider
  names it prints.

## Related skills

- `flutter-architecture`: detection, each pattern's rules, and the checker this
  skill runs (if your agent doesn't auto-load skills, read
  `../flutter-architecture/SKILL.md`). If it isn't installed, the script falls
  back to a minimal built-in scan and says so in `profile source:`.
- `dart-naming`: role names per architecture, which the templates follow
  (`../dart-naming/SKILL.md`, §12 of its reference).
- `flutter-testing`: grow the generated test skeletons
  (`../flutter-testing/SKILL.md`).
- `flutter-error-handling`: the failure flow each profile follows, and how to
  grow the `Failure` set (`../flutter-error-handling/SKILL.md`,
  `../flutter-error-handling/references/error-flow-by-architecture.md`).
- `flutter-secure-defaults`: the checklist the templates follow, and the token
  source and auth interceptor to add to the shared client
  (`../flutter-secure-defaults/SKILL.md`).
- `dart-flutter-best-practices`, `flutter-ui-practices`: for the code you write
  into the TODOs. `dart-flutter-review`: review the finished feature.
