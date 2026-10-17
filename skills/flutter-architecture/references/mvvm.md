# MVVM: the Flutter team's recommended architecture

Source: docs.flutter.dev/app-architecture (concepts, guide, case study, design
patterns) and its reference app, Compass (github.com/flutter/samples/tree/main/compass_app).
The guide describes itself as "guidelines, not steadfast rules, and you should
adapt them to your unique requirements". Report deviations at that strength.

## Contents

1. What it is
2. Layers and roles
3. Allowed dependencies
4. Folder layout
5. State, events and side effects
6. Commands and Result
7. Dependency injection and testing
8. Where MVVM differs from the other patterns
9. Pattern-specific anti-patterns
10. A good example
11. Reviewing an MVVM codebase

## 1. What it is

Separation of concerns is "the most important principle". The app is split into
a **UI layer** (views and view models) and a **data layer** (repositories and
services), with an **optional domain layer** of use cases in between for complex
apps. In MVVM terms, repositories and services are the *Model*.

Each feature has one view, one view model, one or more repositories, and zero or
more services. "Feature" is user-centric: a screen, or a reusable piece of UI
like a logout button with its own `LogoutViewModel`.

## 2. Layers and roles

| Role | Responsibility | Holds state? |
|---|---|---|
| **View** | A composition of widgets (often a screen with a `Scaffold`). Displays view-model data, re-renders on change, wires view-model commands to event handlers | Only ephemeral widget state |
| **View model** | Converts app data into UI state; filters, sorts, combines data from several repositories; keeps the state the view needs to rebuild; exposes **commands** | UI state |
| **Repository** | Source of truth for one type of app data. Polls services, caches, retries, handles errors, refreshes; transforms raw data into **domain models** | App data, app-wide session state |
| **Service** | Wraps one external data source (REST endpoint, platform API, local files). Exposes `Future`/`Stream` responses | No: stateless |
| **Use case** (optional) | Business logic that merges data from several repositories, is very complex, or is reused by several view models | No |

The only logic a **view** may contain:

- simple `if`s that show or hide widgets based on a flag or nullable field in the
  view model
- animation logic
- layout logic based on device information (screen size, orientation)
- simple routing logic

"All logic related to data should be handled in the view model."

## 3. Allowed dependencies

From the case study's "rules of engagement":

| From ↓ may use → | View | View model | Use case | Repository | Service |
|---|---|---|---|---|---|
| **View** | sub-views/widgets | **exactly one** | no | no | no |
| **View model** | never knows the view | (not described; avoid) | yes | **yes**, one or more | no |
| **Use case** | no | no | (rare) | yes, many-to-many | no |
| **Repository** | no | never knows them | no | **never** | yes, many |
| **Service** | no | no | no | never | no |

Key consequences:

- **View models call repositories directly.** "View models are always dependent
  on data repositories." With a domain layer, "view models depend on one or more
  use-cases *and* one or more repositories". Use cases are added "only when
  needed". A view model calling a repository is not a finding in MVVM.
- **Repositories are injected as private fields** on the view model, "otherwise
  views would have direct access to the data layer".
- **Repositories never know about each other.** Combine their data in the view
  model or a use case.
- **Services are private members of repositories**, so the UI can't bypass the
  repository.

## 4. Folder layout

The Compass app's package structure (layer-first at the top, feature folders
inside `ui/`):

```text
lib/
├── ui/
│   ├── core/
│   │   ├── ui/                 # shared widgets
│   │   └── themes/
│   └── <feature>/
│       ├── view_model/
│       │   └── <feature>_viewmodel.dart
│       └── widgets/
│           ├── <feature>_screen.dart
│           └── <other widgets>.dart
├── domain/
│   ├── models/                 # domain models output by repositories
│   └── use_cases/              # optional, only where needed
├── data/
│   ├── repositories/
│   │   └── <type>/<type>_repository.dart   (+ _remote / _local implementations)
│   ├── services/
│   │   └── api/model/          # API models (DTOs)
│   └── model/
├── config/                     # DI setup (dependencies.dart)
├── routing/
├── utils/                      # Result, Command
├── main.dart  main_development.dart  main_staging.dart
```

Feature-first MVVM (`lib/features/<f>/{view,view_model,data}`) is equally
valid. Judge consistency, not the choice. Note the checker flags this layout
`clean_architecture: true` because `domain/use_cases/` exists; that doesn't
make use cases mandatory (see `detect.md` §6).

## 5. State, events and side effects

Unidirectional data flow:

1. The user taps; the view calls a view-model command.
2. The view model calls a repository (or use case) method.
3. The repository updates the data (the single source of truth) and returns it.
4. The view model stores the new UI state and notifies listeners.
5. The view re-renders.

Data can also start in the data layer (a repository polls or streams), in which
case only steps 4–5 happen.

- **UI state is immutable.** Compass uses `freezed` for models and exposes
  lists as `UnmodifiableListView`. For larger screens, consider a dedicated
  `HomeUiState` class.
- **Change notification.** Compass view models extend `ChangeNotifier`; views
  rebuild with `ListenableBuilder`. The guide says Riverpod, flutter_bloc or
  signals work equally well: the pattern is MVVM, the notifier is a detail.
- **App-wide session state** (signed-in user, in-memory caches) lives in
  repositories, which many view models can share.
- **One-time effects** (snackbar on error, navigate on success): the view
  listens to the view model or to a command (`addListener` in `initState`,
  `removeListener` in `dispose`) and acts on the change, clearing the result so
  it doesn't fire again on every `notifyListeners()`.

## 6. Commands and Result

Both are **recommended, not required**.

- A **command** wraps a view-model action and exposes `running`, `error` and
  `completed` (`Command0`, `Command1<T, A>`). It stops double execution while
  running, captures exceptions, and lets views render loading/error UI with
  almost no logic. Commands are created in the view model's constructor
  (`load = Command0(_load)..execute();`). The `command_it` package offers ready
  made ones.
- **`Result<T>`** is a `sealed` class with `Ok<T>` and `Error<T>` subclasses.
  Services and repositories return `Result` instead of throwing, which forces
  callers to handle errors and makes the control flow explicit with `switch`.
  The guide: "This pattern is a recommendation, but not a requirement."

Don't flag the absence of either. Do flag a hand-rolled substitute that has the
bugs commands prevent: separate `isLoadingX`/`errorX` pairs per action that can
contradict each other (`AP-boolean-soup-state`), or errors that are never caught
(`AP-exceptions-across-layers`).

## 7. Dependency injection and testing

- Inject through constructors. Compass uses `package:provider` ("teams at Google
  recommend using `package:provider` to implement dependency injection"):
  services and repositories are `Provider`s at the top of the tree, exposed as
  their **abstract** type (`as BookingRepository`); view models are created in
  the `go_router` route builders with `context.read()`.
- Avoid globally accessible objects. Abstract repositories allow
  development, staging and fake implementations (`BookingRepositoryRemote`,
  `BookingRepositoryLocal`).
- Test each layer separately and together: unit-test view models against fake
  repositories, repositories against fake services, and widget-test views with a
  view model built on fakes.

## 8. Where MVVM differs from the other patterns

- vs **MVN**: MVVM lets the view model call repositories; MVN requires a use
  case. MVVM pass-through use cases are ceremony (`AP-passthrough-usecase`,
  Info); in MVN they're the spec.
- vs **Bloc**: a view model exposes methods/commands; a bloc takes events. Both
  depend on injected repositories.
- vs **Clean Architecture**: the domain layer is optional, and in Compass it
  holds plain domain models rather than entities with behaviour.
- The view gets its view model as a **constructor argument**. A view that
  builds its own view model, or reaches a service locator for one
  (ARCH-104), is drifting from the guide.

## 9. Pattern-specific anti-patterns

See `references/anti-patterns.md` (the index) for full entries; each lives in
`references/anti-patterns/<group>.md` under its `### <ID>` heading.

| ID | In MVVM |
|---|---|
| ARCH-005, ARCH-101, `AP-massive-view` | View doing I/O or data logic. The guide's strongest point |
| ARCH-008 | View imports a repository or use case |
| `AP-viewmodel-exposes-repository` | Repository is a public field, so the view can bypass the view model |
| ARCH-007 | View model imports a concrete repository or service instead of the abstract repository |
| ARCH-009, ARCH-102 | View model imports `material.dart` / holds a `BuildContext` |
| ARCH-010 (low) | View model imports another view model; share through a repository instead |
| ARCH-011 | Repository depends on another repository |
| ARCH-106, `AP-shared-mutable-model` | Mutable models, or public mutable lists the view can edit |
| ARCH-108 | Concrete repository with no abstraction (the guide rates abstract repositories Strong) |
| `AP-god-viewmodel` | One view model serving several unrelated views |
| `AP-boolean-soup-state` | Per-action loading/error flags instead of commands or a sealed state |
| `AP-passthrough-usecase` (Info) | A use case that only forwards to one repository |

Not findings in MVVM: a view model calling repositories directly; no domain
layer; no `Command` class; no `Result` type; `ChangeNotifier` instead of a
third-party library (or the reverse).

## 10. A good example

```dart
// lib/data/repositories/booking/booking_repository.dart
abstract interface class BookingRepository {
  Future<Result<List<BookingSummary>>> getBookingsList();
  Future<Result<void>> delete(int id);
}

// lib/ui/home/view_model/home_viewmodel.dart
final class HomeViewModel extends ChangeNotifier {
  HomeViewModel({required BookingRepository bookingRepository})
      : _bookingRepository = bookingRepository {
    load = Command0(_load)..execute();
    deleteBooking = Command1(_deleteBooking);
  }

  final BookingRepository _bookingRepository; // private: the view can't reach it

  late final Command0<List<BookingSummary>> load;
  late final Command1<void, int> deleteBooking;

  List<BookingSummary> _bookings = const [];
  UnmodifiableListView<BookingSummary> get bookings =>
      UnmodifiableListView(_bookings);

  Future<Result<List<BookingSummary>>> _load() async {
    final result = await _bookingRepository.getBookingsList();
    if (result case Ok(:final value)) _bookings = value;
    notifyListeners();
    return result; // the command exposes running/error/completed to the view
  }

  Future<Result<void>> _deleteBooking(int id) async {
    final result = await _bookingRepository.delete(id);
    if (result is Ok<void>) await _load();
    return result;
  }
}

// lib/ui/home/widgets/home_screen.dart
class HomeScreen extends StatelessWidget {
  const HomeScreen({super.key, required this.viewModel});

  final HomeViewModel viewModel;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: ListenableBuilder(
        listenable: viewModel.load,
        builder: (context, _) {
          if (viewModel.load.running) {
            return const Center(child: CircularProgressIndicator());
          }
          if (viewModel.load.error) {
            return ErrorIndicator(onRetry: viewModel.load.execute);
          }
          return ListenableBuilder(
            listenable: viewModel,
            builder: (context, _) => ListView(
              children: [
                for (final b in viewModel.bookings)
                  Dismissible(
                    key: ValueKey(b.id),
                    onDismissed: (_) => viewModel.deleteBooking.execute(b.id),
                    child: BookingTile(booking: b),
                  ),
              ],
            ),
          );
        },
      ),
    );
  }
}

// lib/routing/router.dart (composition root)
GoRoute(
  path: Routes.home,
  builder: (context, state) =>
      HomeScreen(viewModel: HomeViewModel(bookingRepository: context.read())),
);
```

`Result`, `Ok`, `Error` and `Command0/1` are the Compass `utils/` classes (or
`command_it`). `Error` there shadows `dart:core`'s `Error`; Compass accepts that,
and some projects rename it `Failure`.

## 11. Reviewing an MVVM codebase

- [ ] Views receive their view model (constructor or provider) and contain only
      show/hide, animation, layout and simple routing logic.
- [ ] No view imports a repository, service, use case, DTO or I/O package
      (ARCH-005/006/008, ARCH-101).
- [ ] One view ↔ one view model. No view model serves unrelated screens.
- [ ] View models depend on abstract repositories (and optional use cases),
      held as private fields; no `BuildContext`, no `material.dart`.
- [ ] UI state is immutable or exposed read-only; loading/error per action is
      modelled with commands or a sealed state, not loose flags.
- [ ] Repositories: one per data type, output domain models, own caching/retry/
      error mapping, never import each other, keep services private.
- [ ] Services are stateless, one per data source.
- [ ] Use cases exist only where logic is merged, complex or reused (Info if
      pass-through).
- [ ] DI happens at the composition root; no global singletons reached from
      widgets.
- [ ] View models and repositories have unit tests against fakes.
