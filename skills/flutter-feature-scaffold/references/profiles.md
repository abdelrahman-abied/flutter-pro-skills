# flutter-feature-scaffold: what each profile generates

Moved out of `SKILL.md` so writing a feature loads less: read it when you need
the exact files per profile, how conventions are inferred, or what is left out
on purpose. Paths are relative to the skill folder.

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
