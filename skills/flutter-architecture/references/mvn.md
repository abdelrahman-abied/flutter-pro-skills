# MVN: Model-View-Notifier with Riverpod

Source: the MVN spec by its author, Abdulrahman Abied
(abdelrahman-abied.github.io/mvn-architecture-pattern). The spec's own
scaffolding skill is `mvn` (listed as `mvn-architect:mvn` in some agents); it is
the companion to the "Clean Architecture and MVN with RiverPod" VS Code
extension, and generated code must drop into the folders that extension
creates. This file summarises the spec for **judging** code. Anything not in
the spec is marked *Not in the spec*.

Under precedence rule 2, the MVN spec is the canonical source for MVN apps. It
is stricter than the Flutter MVVM guide on purpose. Don't soften MVN rules
because MVVM allows something, and don't apply MVN rules to non-MVN apps.

## Contents

1. What it is
2. Layers and roles
3. The dependency rule and allowed dependencies
4. Canonical folder layout
5. State, events and side effects
6. Riverpod codegen conventions
7. DI and testing
8. Dart conventions the spec mandates
9. Pattern-specific anti-patterns
10. A good example
11. Reviewing an MVN codebase

## 1. What it is

MVN is Clean Architecture layering (domain / data / presentation per feature)
with a presentation pattern in which the bridge between View and Model is a
Riverpod **`Notifier`**: never a "ViewModel", "Controller" or "VM". Notifiers
and providers are written with Riverpod code generation (`@riverpod`).

The runtime flow is one-directional:
**View → Notifier → UseCase → Repository → Source**.

## 2. Layers and roles

| Layer | Role | Spec rule |
|---|---|---|
| domain | **Entity** | Plain, deeply immutable business object (`@immutable`, all fields `final`). No JSON, no framework types |
| domain | **Repository contract** | `abstract interface class <Feature>Repository`. The domain owns the contract and never knows the implementation |
| domain | **Use case** | One class per intent (`FetchTrendingMovies`), constructor-injected with the **abstract** repository, exposing a single `call()`. The class has no `data/` import |
| data | **Request / Response models** | DTOs, not entities. `<feature>_request.dart` has `toJson`; `<feature>_response.dart` has `fromJson` and `toEntity()`. DTOs never leave the data layer |
| data | **Repository impl** | `<Feature>RepositoryImpl implements <Feature>Repository`, depends on a source, maps responses to entities |
| data | **Source** | Isolates the transport (REST, database, cache) behind a small interface. A leaf: never reads or watches UI state or notifiers |
| presentation | **Notifier** | Class name ends in `Notifier`, `@riverpod`, extends the generated `_$<Name>`. Orchestrates use cases and maps results onto state. No widgets, no `BuildContext`, no raw repository or source access |
| presentation | **State** | A `sealed class` with `final` variant subclasses (`Initial`, `Loading`, `Success`, `Error`), deeply immutable, for exhaustive `switch` |
| presentation | **View** | `ConsumerWidget`/`ConsumerStatefulWidget` with zero business logic, repository references or data formatting. Renders state with an exhaustive `switch` expression |
| presentation | **Widget** | Granular, often `const` sub-widgets extracted from the view to bound rebuilds |
| core | — | Cross-feature: theme, network client, errors, DI, utils |

## 3. The dependency rule and allowed dependencies

Dependencies point inward: **presentation → domain ← data**. Domain is the
centre and depends on nothing else. Data implements domain. Presentation
consumes domain.

| From ↓ may import → | entity | repo contract | use case | DTO | repo impl | source | notifier | state | view/widget |
|---|---|---|---|---|---|---|---|---|---|
| **entity** | yes | — | — | no | no | no | no | no | no |
| **repo contract** | yes | — | — | no | no | no | no | no | no |
| **use case class** | yes | **yes** | — | no | no | no | no | no | no |
| **use-case provider** (same file, `@riverpod`) | yes | yes | yes | no | **yes: the DI seam** | no | no | no | no |
| **DTO** (request/response) | yes (`toEntity`) | no | no | yes | no | no | no | no | no |
| **repo impl** | yes | yes | no | yes | — | yes | no | no | no |
| **source** | no | no | no | yes | no | — | **never** | **never** | no |
| **notifier** | yes | **no** | **yes** | no | **no** | **no** | yes, `ref.watch` in `build()` | yes | no |
| **state** | yes | no | no | no | no | no | no | yes | no |
| **view / widget** | yes | no | no | no | no | no | yes (its provider) | yes | yes |

The **DI seam**: the use-case *provider*, co-located with the use case under
`domain/usecases/`, wires the use case to the repository provider declared in
`data/repositories/`. That import is "the single sanctioned spot where a
domain-adjacent file imports the data provider", acceptable "precisely because
the use-case *class* stays pure". `arch_check.py` puts that import in
`suppressed` with the reason "MVN DI seam (use-case provider)" instead of
reporting ARCH-001. It also allows `riverpod_annotation`/`riverpod` in
`domain/usecases/` under the mvn profile (ARCH-003).

What the spec rules out, and the matching IDs:

- a notifier importing a repository, repository impl, source or service
  (ARCH-012; ARCH-007 for concrete ones)
- domain importing data (ARCH-001, except the seam), presentation (ARCH-002),
  Flutter or UI Riverpod (ARCH-003)
- a view doing I/O (ARCH-005, ARCH-101), holding repository references
  (ARCH-008) or formatting data (`AP-massive-view`)
- DTOs in presentation (ARCH-006, `AP-dto-as-ui-state`)
- domain code that watches or reads UI state or notifiers

## 4. Canonical folder layout

The spec calls this tree "binding". Folder names are **singular**: `notifier`,
`state`, `view`, `widget`.

```text
lib/
├── core/                         # cross-feature: theme, network client, errors, DI, utils
└── features/
    └── <feature>/
        ├── domain/               # pure Dart: no Flutter, no Riverpod-of-UI, no data imports
        │   ├── entities/<feature>_entity.dart
        │   ├── repositories/<feature>_repository.dart      # abstract contract
        │   └── usecases/<feature>_usecase.dart             # one intent per use case (+ its provider)
        ├── data/
        │   ├── models/<feature>_request.dart               # outbound DTO
        │   ├── models/<feature>_response.dart              # inbound DTO + toEntity()
        │   ├── repositories/<feature>_repository_impl.dart # implements the contract (+ its provider)
        │   └── sources/<feature>_source.dart               # remote/local source (+ its provider)
        └── presentation/
            ├── notifier/<feature>_notifier.dart            # extends _$<Feature>Notifier
            ├── state/<feature>_state.dart                  # sealed state
            ├── view/<feature>_view.dart                    # ConsumerWidget
            └── widget/<feature>_widget.dart                # granular sub-widgets
```

Banned: any `controller`/`controllers` folder or class, and any `viewmodel`/`vm`
naming (ARCH-112). Animation controllers are the only allowed use of the word
"Controller". The extension seeds `widget/<feature>_widget.dart`; renaming it
or adding descriptively named widgets (`movie_list.dart`) in that folder is
expected.

When refactoring an existing feature into MVN, the spec says to map each file
to its canonical home, hoist abstract repository contracts into
`domain/repositories/`, push implementations to `data/`, split entities
(domain) from DTOs (`data/models`), and rename any controller/view model to a
`Notifier` under `presentation/notifier/`.

## 5. State, events and side effects

- **State** is a `sealed` hierarchy of `final` classes, deeply immutable. The
  view switches over it exhaustively with a `switch` **expression** and no
  `default`/wildcard that would hide a missing state.
- **Events** are plain notifier methods (`loadTrending()`), called from the
  view with `ref.read(provider.notifier)`. The spec prefers tear-offs when the
  signature matches: `onPressed: ref.read(p.notifier).loadTrending`.
- **One-time side effects** (toasts, navigation, sheets) go through
  `ref.listen()` inside the view's `build()`. Never store transient events as
  mutable booleans in the state class (ARCH-111).
- **Notifier → notifier**: when a notifier depends on another's state,
  establish a reactive link with `ref.watch(otherProvider)` **inside
  `build()`**, "never imperative cross-controller mutation". So ARCH-010
  (sibling-logic-dependency) does **not** apply to MVN; what MVN forbids is one
  notifier calling methods on another or writing to its state.
- **Reads vs watches**: `ref.watch` for reactive dependencies, `ref.read` for
  one-shot calls inside notifier methods and callbacks.

## 6. Riverpod codegen conventions

- Modern syntax only: providers and notifiers use `@riverpod` with
  `part '<file>.g.dart';`. Notifiers extend `_$<Name>`. **No legacy
  `StateNotifierProvider` or `ChangeNotifier`** (`AP-mvn-legacy-riverpod-syntax`).
- Riverpod 3: function providers take the generic `Ref ref`, not the removed
  per-provider `*Ref` types (`MovieRepositoryRef` no longer exists).
- Generate with `dart run build_runner build -d` (or `watch`). Never hand-edit
  `*.g.dart`.
- The repository provider lives in the data layer and returns the **abstract**
  type, so consumers depend on the contract.
- *Not in the spec:* riverpod_generator 3.x names the provider for
  `class MovieNotifier` `movieProvider` (it drops the `Notifier` suffix); 2.x
  names it `movieNotifierProvider`. Use whatever the generated file declares.

## 7. DI and testing

The generated providers are "the only place a concrete implementation is bound
to an abstraction". So:

- source provider → `MovieSource` (abstract) bound to `MovieRemoteSource`
- repository provider (in `data/`) → `MovieRepository` bound to `MovieRepositoryImpl`
- use-case provider (in `domain/usecases/`) → the use case, given the repository provider
- the notifier reads the use-case provider

*Not in the spec (testing advice that follows from it):* because each binding
is a provider, tests override them instead of mocking globals:

```dart
final container = ProviderContainer(
  overrides: [
    fetchTrendingMoviesProvider.overrideWithValue(
      FetchTrendingMovies(FakeMovieRepository()),
    ),
  ],
);
addTearDown(container.dispose);
```

Unit-test use cases with a fake repository, repository implementations with a
fake source, notifiers through a `ProviderContainer` with an overridden
use-case provider, and views with `ProviderScope(overrides: […])`.

## 8. Dart conventions the spec mandates

- Mirror `flutter_lints` + `very_good_analysis`, and enable
  `riverpod_lint`/`custom_lint`.
- `const` constructors and literals wherever allowed.
- Exhaustive `switch` expressions over sealed classes, no hiding `default`
  (`AP-default-hides-missing-state`).
- Targeted rebuilds: `ref.watch(provider.select((s) => s.field))` when a widget
  needs one property.
- Reject monolithic `build()` methods. A subtree with its own logic, or one that
  watches a provider, becomes its own widget under `widget/`.
- Real value equality (`freezed`, `equatable`, or manual `==`/`hashCode`) for
  state and entities that feed `.select()` or comparisons: `@immutable` alone
  only gives reference equality.

Naming tables (file names, suffixes) live in the `dart-naming` skill.

## 9. Pattern-specific anti-patterns

| ID | In MVN |
|---|---|
| ARCH-012 | Notifier imports a repository/source/service instead of a use case |
| ARCH-112 | `ViewModel`/`VM`/`Controller` classes or `controller(s)/`/`view_model(s)/` folders |
| `AP-mvn-legacy-riverpod-syntax` | `StateNotifier`, `ChangeNotifierProvider`, hand-written providers, per-provider `*Ref` types |
| ARCH-111 | `showError`/`navigateToX` bools in state instead of `ref.listen` |
| ARCH-106 | Non-final fields in state classes |
| ARCH-109 | `TextEditingController` & co. created in a notifier or provider |
| ARCH-110 | `ref.read(p.notifier).load()` in `initState` |
| `AP-riverpod-side-effects-in-provider-build` | Writes or network posts in a provider's/notifier's `build()` |
| `AP-riverpod-dynamic-providers` | Providers created inside classes or functions |
| ARCH-001/002/003 | Domain impurity, except the DI seam |
| `AP-default-hides-missing-state` | `_ =>`/`default` in a switch over the sealed state |

**Not findings in MVN**: a use case that only forwards to the repository
(`AP-passthrough-usecase` is prescribed structure here); `ref.watch(other)` in a
notifier's `build()` (ARCH-010 is off); the use-case provider importing the
repository implementation's provider (the seam); `riverpod_annotation` in
`domain/usecases/`.

## 10. A good example

The spec's golden reference, abridged (entities, contract, DTOs and source as in
§2; full template in the `mvn` skill):

```dart
// domain/usecases/movie_usecase.dart
import 'package:riverpod_annotation/riverpod_annotation.dart';

import '../entities/movie_entity.dart';
import '../repositories/movie_repository.dart';
// DI seam: the use-case PROVIDER may reference the data provider; the class stays pure.
import '../../data/repositories/movie_repository_impl.dart';

part 'movie_usecase.g.dart';

class FetchTrendingMovies {
  final MovieRepository _repository;
  const FetchTrendingMovies(this._repository);

  Future<List<MovieEntity>> call() => _repository.fetchTrending();
}

@riverpod
FetchTrendingMovies fetchTrendingMovies(Ref ref) =>
    FetchTrendingMovies(ref.watch(movieRepositoryProvider));
```

```dart
// presentation/state/movie_state.dart
@immutable
sealed class MovieState {
  const MovieState();
}

final class MovieInitial extends MovieState { const MovieInitial(); }
final class MovieLoading extends MovieState { const MovieLoading(); }
final class MovieSuccess extends MovieState {
  final List<MovieEntity> movies;
  const MovieSuccess(this.movies);
}
final class MovieError extends MovieState {
  final String message;
  const MovieError(this.message);
}
```

```dart
// presentation/notifier/movie_notifier.dart
part 'movie_notifier.g.dart';

@riverpod
class MovieNotifier extends _$MovieNotifier {
  @override
  MovieState build() => const MovieInitial();

  Future<void> loadTrending() async {
    state = const MovieLoading();
    try {
      final movies = await ref.read(fetchTrendingMoviesProvider)();
      state = MovieSuccess(movies);
    } catch (e) {
      state = MovieError(e.toString());
    }
  }
}
```

```dart
// presentation/view/movie_view.dart
class MovieView extends ConsumerWidget {
  const MovieView({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    // One-time side effects, outside the paint pipeline.
    ref.listen<MovieState>(movieNotifierProvider, (previous, current) {
      if (current is MovieError) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text(current.message)));
      }
    });

    final state = ref.watch(movieNotifierProvider);

    return Scaffold(
      appBar: AppBar(title: const Text('Clean Architecture + MVN')),
      body: switch (state) {
        MovieInitial() => Center(
            child: ElevatedButton(
              onPressed: ref.read(movieNotifierProvider.notifier).loadTrending,
              child: const Text('Fetch Trends'),
            ),
          ),
        MovieLoading() => const Center(child: CircularProgressIndicator()),
        MovieError(message: final m) => Center(child: Text(m)),
        MovieSuccess(movies: final list) => MovieList(movies: list),
      },
    );
  }
}
```

A notifier that depends on another notifier, the sanctioned way:

```dart
@riverpod
class CartTotalNotifier extends _$CartTotalNotifier {
  @override
  Money build() {
    final cart = ref.watch(cartNotifierProvider); // reactive link inside build()
    return switch (cart) {
      CartLoaded(:final items) => items.fold(Money.zero, (sum, i) => sum + i.price),
      CartInitial() || CartLoading() || CartError() => Money.zero,
    };
  }
}
```

*Not in the spec:* after an `await` in a notifier method, Riverpod 3 offers
`ref.mounted` to check the notifier wasn't disposed before writing `state`.

## 11. Reviewing an MVN codebase

- [ ] Every feature follows the tree in §4, with singular folder names.
- [ ] No `ViewModel`/`VM`/`Controller` classes or folders (animation and other
      Flutter controllers excepted).
- [ ] Domain is pure Dart: entities immutable, contracts are
      `abstract interface class`, use-case classes import only the contract
      and entities. The only data import in `domain/` is the use-case
      provider's seam.
- [ ] DTOs (`*_request.dart`, `*_response.dart`) stay in `data/`; repositories
      return entities via `toEntity()`.
- [ ] Sources are leaves behind an interface; they never touch UI state.
- [ ] Notifiers use `@riverpod`, extend `_$X`, call use cases (never
      repositories or sources), hold no `BuildContext` and import no widgets.
- [ ] Notifier-to-notifier links are `ref.watch` inside `build()`, never
      imperative calls on another notifier.
- [ ] State is a sealed hierarchy of `final`, immutable classes with real
      equality where `.select()` is used.
- [ ] Views are `ConsumerWidget`s that switch exhaustively over state, use
      `ref.listen` for one-time effects, and contain no logic or formatting.
- [ ] No `StateNotifierProvider`/`ChangeNotifier`, no per-provider `*Ref`
      types on Riverpod 3, no hand-edited `*.g.dart`.
- [ ] `riverpod_lint`/`custom_lint` enabled.
