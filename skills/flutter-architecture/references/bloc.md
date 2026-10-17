# Bloc and Cubit

Source: bloclibrary.dev (Architecture, Naming Conventions, Modeling State) and
the `bloc`/`flutter_bloc` API. Bloc's naming and state-modelling pages call
themselves "simply recommendations and completely optional". The architecture
page is firmer: a bloc listening to another bloc is something "you should
**not** do". Report at those strengths.

## Contents

1. What it is
2. Layers and roles
3. Allowed dependencies
4. Folder layout
5. State, events and side effects
6. Bloc-to-bloc: the sanctioned alternatives
7. DI and testing
8. Pattern-specific anti-patterns
9. A good example
10. Reviewing a Bloc codebase

## 1. What it is

Bloc separates an app into three layers: **presentation**, **business logic**
and **data** (split into repositories and data providers). A **Bloc** turns
incoming *events* into outgoing *states*; a **Cubit** is the lighter variant
that exposes methods and calls `emit` directly. Both expose a stream of states
that widgets rebuild from.

Bloc is a presentation-plus-logic pattern. It says nothing mandatory about a
domain layer; many Bloc apps add Clean Architecture use cases, many don't.

## 2. Layers and roles

| Layer | Role | Responsibility |
|---|---|---|
| Data | **Data provider** | Provides raw data. Generic and versatile; usually simple CRUD APIs (`readData`, `createData`). The API client, database or plugin wrapper |
| Data | **Repository** | A wrapper around one or more data providers. Combines and transforms raw data before handing it to the business-logic layer |
| Business logic | **Bloc / Cubit** | Responds to input from the presentation layer with new states. Depends on one or more injected repositories. "The bridge between the user interface and the data layer" |
| Presentation | **Widgets** (page, view) | Figures out how to render itself from one or more bloc states; handles user input and app lifecycle events (e.g. adds an `AppStarted`-style event) |

## 3. Allowed dependencies

| From ↓ may use → | Widgets | Bloc/Cubit | Repository | Data provider |
|---|---|---|---|---|
| **Widgets** | yes | yes, via `BlocProvider`/`context.read`/`BlocBuilder` | only to **create** blocs (`RepositoryProvider`, `context.read<Repo>()` in a `BlocProvider`) | no |
| **Bloc/Cubit** | no | **no** (bloc-to-bloc) | **yes**, constructor-injected | no |
| **Repository** | no | no | **no** | yes, one or more |
| **Data provider** | no | no | no | no |

"A bloc should only receive information through events and from injected
repositories (i.e., repositories given to the bloc in its constructor)."
"Since blocs reside in the business logic architectural layer, no bloc should
know about any other bloc."

## 4. Folder layout

The bloclibrary tutorials (flutter_todos, flutter_weather) use feature folders
with a barrel file, and put the data layer in separate Dart packages. This is
the tutorials' convention, not a rule:

```text
lib/
├── app/                        # App widget, theme, BlocObserver
├── todos_overview/
│   ├── todos_overview.dart     # barrel: exports bloc/, view/, widgets/
│   ├── bloc/
│   │   ├── todos_overview_bloc.dart
│   │   ├── todos_overview_event.dart   # part of the bloc
│   │   └── todos_overview_state.dart   # part of the bloc
│   ├── view/
│   │   └── todos_overview_page.dart    # Page provides the bloc, View renders it
│   └── widgets/
└── main.dart
packages/
├── todos_api/                  # data provider interface + models
├── local_storage_todos_api/    # data provider implementation
└── todos_repository/           # repository
```

Because the repository and API live in path packages, `arch_check.py` sees them
as external dependencies and can't check their internals. Read them separately.
A single-package app with `lib/data/{repositories,providers}/` is equally fine.

The **Page/View split** used in the tutorials: `TodosOverviewPage` creates the
bloc with `BlocProvider` and `context.read<TodosRepository>()`; the private or
sibling `TodosOverviewView` reads it. That's why ARCH-008 exempts files that
contain `BlocProvider(`, `RepositoryProvider(` or `MultiRepositoryProvider(`.

## 5. State, events and side effects

**Events** (Bloc, not Cubit) are past-tense facts from the bloc's point of view
(`TodosOverviewSubscriptionRequested`, `TodoDeleted`). Initial load events end
in `Started`. Full naming anatomy is in the `dart-naming` skill.

**State** comes in two sanctioned shapes. Both are fine; pick per bloc:

| Shape | Best for | Cost |
|---|---|---|
| **Sealed class + subclasses** (`WeatherInitial`, `WeatherLoadInProgress`, `WeatherLoadSuccess`, `WeatherLoadFailure`) | well-defined, exclusive states | verbose; shared fields repeated |
| **Single class + status enum** (`WeatherState(status: WeatherStatus.loading, weather: …)`) | states that aren't exclusive or share many fields, e.g. showing a snackbar on error *while still showing the last data* | not type safe; nullable fields; can emit a malformed state |

So under Bloc, a single state class with a `status` enum is **not**
`AP-boolean-soup-state`. Boolean soup is several independent bools and
nullables with no status discriminator.

State should be immutable with value equality (`equatable`, `freezed`, or
manual `==`). Bloc skips emitting a state equal to the current one, so mutating
a state object in place and re-emitting it doesn't rebuild the UI (ARCH-106).

**Side effects** that must happen once (navigation, snackbars, dialogs) go in a
`BlocListener` (or the `listener` of `BlocConsumer`), not in `BlocBuilder`'s
`builder` and not in the bloc. Rebuild-only logic goes in `BlocBuilder`,
`BlocSelector` or `context.select`.

**Concurrency**: event handlers registered with `on<E>` run concurrently by
default; use `transformer:` with `bloc_concurrency` (`droppable()`,
`restartable()`, `sequential()`) when order or de-duplication matters.

## 6. Bloc-to-bloc: the sanctioned alternatives

The tight-coupling version bloclibrary warns against:

```dart
// Bad: SecondBloc knows about FirstBloc.
class SecondBloc extends Bloc<SecondEvent, SecondState> {
  SecondBloc({required FirstBloc firstBloc}) : super(const SecondInitial()) {
    _sub = firstBloc.stream.listen((s) => add(FirstChanged(s)));
  }
  late final StreamSubscription<FirstState> _sub;

  @override
  Future<void> close() {
    _sub.cancel();
    return super.close();
  }
}
```

It works and even cleans up after itself, but "sibling dependencies between two
entities in the same architectural layer should be avoided at all costs".
Two options instead:

1. **Up, through presentation**: a `BlocListener<FirstBloc, FirstState>` adds
   an event to `SecondBloc`. (The flutter_weather tutorial changes the theme
   from weather this way.)
2. **Down, through the domain/data layer**: both blocs subscribe to the same
   reactive repository stream and update independently. Common in large apps.

```dart
// Good (option 1)
BlocListener<WeatherBloc, WeatherState>(
  listenWhen: (prev, curr) => prev.weather != curr.weather,
  listener: (context, state) =>
      context.read<ThemeCubit>().updateTheme(state.weather),
  child: const WeatherView(),
);
```

This is where Bloc and MVN disagree: MVN sanctions `ref.watch(otherProvider)`
inside a notifier's `build()`. Don't carry either rule across.

## 7. DI and testing

- Repositories go in `RepositoryProvider`/`MultiRepositoryProvider` near the
  root; blocs are created with `BlocProvider(create: …)` and given repositories
  from `context.read`. `BlocProvider` closes the bloc it created.
- Some apps use `get_it` instead; that's fine as long as blocs still receive
  repositories through the constructor, not by calling the locator inside the
  bloc.
- Test blocs with `bloc_test`'s `blocTest` (build with a fake/mock repository,
  `act` by adding events, `expect` the emitted states). Test widgets by
  providing a mocked bloc (`MockBloc`/`whenListen`).

## 8. Pattern-specific anti-patterns

| ID | In Bloc |
|---|---|
| ARCH-010 (medium), `AP-bloc-to-bloc` | A bloc imports, receives or listens to another bloc/cubit |
| ARCH-102, `AP-navigation-in-logic` | `BuildContext`, `Navigator`, `showDialog` inside a bloc; use `BlocListener` |
| ARCH-009 | Bloc imports `material.dart` (often for `Color`/`IconData` in state) |
| ARCH-007 | Bloc imports a data provider, `dio`, `http` or a concrete repository impl |
| ARCH-106 | Non-final state fields; mutated-and-re-emitted states that never rebuild |
| ARCH-111 | `shouldNavigate`/`showDialog` bools in state instead of a listener |
| `AP-god-viewmodel` | One bloc driving several unrelated screens; split by feature |
| `AP-stream-subscription-in-widget` | Widget subscribes to `bloc.stream` by hand instead of `BlocListener` |
| ARCH-101 | Widgets doing I/O instead of adding an event |

Not findings in Bloc: a bloc depending on several repositories; no use cases;
a page widget that reads a repository to construct its bloc; the single-class +
status-enum state shape; Cubits for simple state alongside Blocs for complex
flows.

## 9. A good example

```dart
// todos_overview/bloc/todos_overview_event.dart
part of 'todos_overview_bloc.dart';

sealed class TodosOverviewEvent {
  const TodosOverviewEvent();
}

final class TodosOverviewSubscriptionRequested extends TodosOverviewEvent {
  const TodosOverviewSubscriptionRequested();
}

final class TodosOverviewTodoDeleted extends TodosOverviewEvent {
  const TodosOverviewTodoDeleted(this.todo);
  final Todo todo;
}
```

```dart
// todos_overview/bloc/todos_overview_state.dart
part of 'todos_overview_bloc.dart';

enum TodosOverviewStatus { initial, loading, success, failure }

final class TodosOverviewState extends Equatable {
  const TodosOverviewState({
    this.status = TodosOverviewStatus.initial,
    this.todos = const [],
  });

  final TodosOverviewStatus status;
  final List<Todo> todos;

  TodosOverviewState copyWith({TodosOverviewStatus? status, List<Todo>? todos}) =>
      TodosOverviewState(status: status ?? this.status, todos: todos ?? this.todos);

  @override
  List<Object> get props => [status, todos];
}
```

```dart
// todos_overview/bloc/todos_overview_bloc.dart
class TodosOverviewBloc extends Bloc<TodosOverviewEvent, TodosOverviewState> {
  TodosOverviewBloc({required TodosRepository todosRepository})
      : _todosRepository = todosRepository,
        super(const TodosOverviewState()) {
    on<TodosOverviewSubscriptionRequested>(_onSubscriptionRequested);
    on<TodosOverviewTodoDeleted>(_onTodoDeleted);
  }

  final TodosRepository _todosRepository;

  Future<void> _onSubscriptionRequested(
    TodosOverviewSubscriptionRequested event,
    Emitter<TodosOverviewState> emit,
  ) async {
    emit(state.copyWith(status: TodosOverviewStatus.loading));
    await emit.forEach<List<Todo>>(
      _todosRepository.getTodos(),
      onData: (todos) =>
          state.copyWith(status: TodosOverviewStatus.success, todos: todos),
      onError: (error, stackTrace) => state.copyWith(status: TodosOverviewStatus.failure),
    );
  }

  Future<void> _onTodoDeleted(
    TodosOverviewTodoDeleted event,
    Emitter<TodosOverviewState> emit,
  ) =>
      _todosRepository.deleteTodo(event.todo.id);
}
```

```dart
// todos_overview/view/todos_overview_page.dart
class TodosOverviewPage extends StatelessWidget {
  const TodosOverviewPage({super.key});

  @override
  Widget build(BuildContext context) {
    return BlocProvider(
      create: (context) => TodosOverviewBloc(
        todosRepository: context.read<TodosRepository>(),
      )..add(const TodosOverviewSubscriptionRequested()),
      child: const TodosOverviewView(),
    );
  }
}

class TodosOverviewView extends StatelessWidget {
  const TodosOverviewView({super.key});

  @override
  Widget build(BuildContext context) {
    return BlocListener<TodosOverviewBloc, TodosOverviewState>(
      listenWhen: (prev, curr) => prev.status != curr.status,
      listener: (context, state) {
        if (state.status == TodosOverviewStatus.failure) {
          ScaffoldMessenger.of(context)
            ..hideCurrentSnackBar()
            ..showSnackBar(const SnackBar(content: Text('Could not load todos')));
        }
      },
      child: BlocBuilder<TodosOverviewBloc, TodosOverviewState>(
        builder: (context, state) => switch (state.status) {
          TodosOverviewStatus.initial ||
          TodosOverviewStatus.loading when state.todos.isEmpty =>
            const Center(child: CircularProgressIndicator()),
          _ => TodoList(
              todos: state.todos,
              onDelete: (todo) => context
                  .read<TodosOverviewBloc>()
                  .add(TodosOverviewTodoDeleted(todo)),
            ),
        },
      ),
    );
  }
}
```

The `_ =>` here is deliberate: with a status enum and non-exclusive states,
"show the list we have" is the right fallback for loading-with-data, success
and failure (the snackbar reports the failure).

## 10. Reviewing a Bloc codebase

- [ ] Blocs and cubits receive repositories through the constructor and nothing
      else: no other blocs, no data providers, no service-locator calls inside.
- [ ] No bloc imports another bloc; cross-bloc reactions go through a
      `BlocListener` or a shared repository stream.
- [ ] No `BuildContext`, `Navigator` or `material.dart` inside blocs.
- [ ] Events are past-tense facts; states are nouns (see `dart-naming`).
- [ ] State is immutable with value equality; the chosen shape (sealed vs
      status enum) fits whether the states are exclusive.
- [ ] One-time effects live in `BlocListener`/`BlocConsumer.listener`, never in
      `builder` and never as bools in state.
- [ ] Widgets create blocs with `BlocProvider` (which closes them) and never do
      I/O themselves.
- [ ] Repositories wrap data providers, return domain models, and don't know
      about each other.
- [ ] Event handlers that must not overlap use a `bloc_concurrency` transformer.
- [ ] Blocs are tested with `blocTest` against fake repositories.
