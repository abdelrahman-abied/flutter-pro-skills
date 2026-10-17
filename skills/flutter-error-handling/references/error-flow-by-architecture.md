# Error flow by architecture

Every pattern below follows the same four steps, with different idioms:

1. **Source/service** does I/O and may throw transport exceptions.
2. **Repository** maps them to typed domain failures, which it throws or returns
   in a `Result`.
3. **Logic** turns a failure into UI state.
4. **UI** renders that state, and shows one-time effects (snackbars, dialogs)
   from a listener.

What escapes all four reaches the global handlers (`references/global-handlers.md`).

The examples share the `Failure` set and the `Result` type from
`references/result-vs-exceptions.md`, and `failureText(l10n, failure)`, which
maps a failure to localized text in the UI.

## Contents

- 1. MVN (Riverpod codegen + Clean Architecture)
- 2. MVVM with Command and Result (the Flutter team's guide)
- 3. Bloc and Cubit
- 4. Clean Architecture with Either (fpdart)
- 5. Riverpod without MVN (AsyncValue)
- 6. Provider + ChangeNotifier
- 7. GetX
- 8. setState
- Cross-cutting: keeping data on refresh failure, retry buttons, logging once

## 1. MVN (Riverpod codegen + Clean Architecture)

The MVN spec's chain is View → Notifier → UseCase → Repository → Source. The
notifier "orchestrates use cases and maps results onto state". State is a
`sealed` class with `Initial`/`Loading`/`Success`/`Error` variants. One-time
effects go through `ref.listen()` inside `build()`. The spec's example catches
in the notifier (`catch (e) { state = MovieError(e.toString()); }`). The
version below keeps that shape, but maps to a typed failure in the repository,
so the view never shows `e.toString()` (ERR-008).

```dart
// data/sources/movie_source.dart: throws DioException (fine for a source)
abstract interface class MovieSource {
  Future<List<MovieResponse>> getTrending();
}

class MovieRemoteSource implements MovieSource {
  MovieRemoteSource(this._dio);
  final Dio _dio;

  @override
  Future<List<MovieResponse>> getTrending() async {
    final res = await _dio.get<List<dynamic>>('/movies/trending');
    return [for (final j in res.data ?? const []) MovieResponse.fromJson(j as Map<String, dynamic>)];
  }
}
```

```dart
// data/repositories/movie_repository_impl.dart: the mapping boundary
class MovieRepositoryImpl implements MovieRepository {
  const MovieRepositoryImpl(this._source);
  final MovieSource _source;

  @override
  Future<List<MovieEntity>> fetchTrending() async {
    try {
      final responses = await _source.getTrending();
      return [for (final r in responses) r.toEntity()];
    } on DioException catch (e, st) {
      Error.throwWithStackTrace(mapDio(e, st), st);   // NetworkFailure, ServerFailure, ...
    } on FormatException catch (e, st) {
      Error.throwWithStackTrace(ParseFailure(cause: e, stackTrace: st), st);
    }
  }
}
```

```dart
// domain/usecases/movie_usecase.dart: pass-through (prescribed in MVN); no transport types
class FetchTrendingMovies {
  const FetchTrendingMovies(this._repository);
  final MovieRepository _repository;

  Future<List<MovieEntity>> call() => _repository.fetchTrending();
}
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
  const MovieSuccess(this.movies);
  final List<MovieEntity> movies;
}
final class MovieError extends MovieState {
  const MovieError(this.failure);
  final Failure failure;                  // typed; the view picks the words
}
```

```dart
// presentation/notifier/movie_notifier.dart
@riverpod
class MovieNotifier extends _$MovieNotifier {
  @override
  MovieState build() => const MovieInitial();

  Future<void> loadTrending() async {
    state = const MovieLoading();
    try {
      final movies = await ref.read(fetchTrendingMoviesProvider)();
      state = MovieSuccess(movies);
    } on Failure catch (f) {
      state = MovieError(f);
    } catch (e, st) {
      // Not a mapped failure, so a bug or something unexpected: report it and still leave Loading.
      ref.read(errorReporterProvider).record(e, st);
      state = const MovieError(UnknownFailure());
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
    final l = AppLocalizations.of(context);
    // One-time effect: the snackbar fires once per transition into the error state.
    ref.listen<MovieState>(movieNotifierProvider, (previous, current) {
      if (current is MovieError && previous is! MovieError) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(failureText(l, current.failure))),
        );
      }
    });

    final state = ref.watch(movieNotifierProvider);
    return switch (state) {
      MovieInitial() || MovieLoading() => const Center(child: CircularProgressIndicator()),
      MovieError(:final failure) => ErrorView(
          message: failureText(l, failure),
          onRetry: ref.read(movieNotifierProvider.notifier).loadTrending,
        ),
      MovieSuccess(:final movies) => MovieList(movies: movies),
    };
  }
}
```

MVN review points:
- A notifier that catches with `catch (e)` is the sanctioned boundary. ERR-002
  doesn't apply to it.
- `state = MovieError(e.toString())` is the spec's example. It's acceptable
  only when failures are already user-safe (ERR-008, graded Low in logic).
- Never put a `showError` bool in state (ARCH-111). Use `ref.listen`.
- After an `await`, check `ref.mounted` (Riverpod 3) before setting state in
  long-lived flows.

## 2. MVVM with Command and Result (the Flutter team's guide)

The Compass app returns `Result` from services *and* repositories. View models
expose `Command`s, which capture each action's running/error/completed state.
The full `Command` runs `_result = await action()` inside `try { } finally { }`
with **no catch**, so actions must return `Result` and never throw.

```dart
// data/services/api_client.dart
class ApiClient {
  Future<Result<List<BookingApiModel>>> getBookings() async {
    try {
      final res = await _client.get(_uri('/booking'));
      if (res.statusCode != 200) return Result.error(ServerFailure(res.statusCode));
      final list = jsonDecode(res.body) as List<dynamic>;
      return Result.ok([for (final j in list) BookingApiModel.fromJson(j as Map<String, dynamic>)]);
    } on http.ClientException catch (e, st) {
      return Result.error(NetworkFailure(cause: e, stackTrace: st));
    } on FormatException catch (e, st) {
      return Result.error(ParseFailure(cause: e, stackTrace: st));
    }
  }
}
```

```dart
// data/repositories/booking_repository_remote.dart
class BookingRepositoryRemote implements BookingRepository {
  BookingRepositoryRemote(this._api);
  final ApiClient _api;

  @override
  Future<Result<List<BookingSummary>>> getBookingsList() async {
    final result = await _api.getBookings();
    return switch (result) {
      Ok(:final value) => Result.ok([for (final b in value) b.toSummary()]),
      Error(:final error) => Result.error(error),
    };
  }
}
```

```dart
// ui/home/view_models/home_viewmodel.dart
class HomeViewModel extends ChangeNotifier {
  HomeViewModel({required BookingRepository bookingRepository}) : _repo = bookingRepository {
    load = Command0(_load)..execute();
    deleteBooking = Command1(_deleteBooking);
  }

  final BookingRepository _repo;
  late final Command0<void> load;
  late final Command1<void, int> deleteBooking;

  List<BookingSummary> _bookings = const [];
  List<BookingSummary> get bookings => _bookings;

  Future<Result<void>> _load() async {
    final result = await _repo.getBookingsList();
    if (result case Ok(:final value)) {
      _bookings = value;
      notifyListeners();
    }
    return result;                 // the Command exposes Error → view
  }

  Future<Result<void>> _deleteBooking(int id) async {
    final result = await _repo.delete(id);
    if (result is Ok) await _load();
    return result;
  }
}
```

```dart
// ui/home/widgets/home_screen.dart
class _HomeScreenState extends State<HomeScreen> {
  @override
  void initState() {
    super.initState();
    widget.viewModel.deleteBooking.addListener(_onDeleteResult);
  }

  @override
  void didUpdateWidget(covariant HomeScreen oldWidget) {
    super.didUpdateWidget(oldWidget);
    oldWidget.viewModel.deleteBooking.removeListener(_onDeleteResult);
    widget.viewModel.deleteBooking.addListener(_onDeleteResult);
  }

  @override
  void dispose() {
    widget.viewModel.deleteBooking.removeListener(_onDeleteResult);
    super.dispose();
  }

  void _onDeleteResult() {
    final cmd = widget.viewModel.deleteBooking;
    if (cmd.result case Error(:final error)) {
      cmd.clearResult();             // consume the one-time event
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(failureText(AppLocalizations.of(context), error))),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    return ListenableBuilder(
      listenable: widget.viewModel.load,
      builder: (context, child) {
        final load = widget.viewModel.load;
        if (load.running) return const Center(child: CircularProgressIndicator());
        if (load.result case Error(:final error)) {
          return ErrorView(
            message: failureText(AppLocalizations.of(context), error),
            onRetry: load.execute,
          );
        }
        return child!;
      },
      child: ListenableBuilder(
        listenable: widget.viewModel,
        builder: (context, _) => BookingList(bookings: widget.viewModel.bookings),
      ),
    );
  }
}
```

MVVM review points:
- If the project uses the *simple* `Command`, whose `execute()` does
  `on Exception catch (error)`, actions may throw `Exception`s. With the full
  Result-based `Command`, a throw inside an action escapes (ERR-009 /
  ERR-result-unguarded-await).
- A view model with hand-rolled `isLoading` + `error` fields must reset both
  on every path (ERR-010). That's what `Command` is for.
- `clearResult()` after showing a snackbar, otherwise it re-fires on every
  `notifyListeners()`.

## 3. Bloc and Cubit

Bloc's own samples throw from the repository (a custom exception), and the
bloc catches it and emits a failure state. Errors thrown inside an event
handler are passed to `onError` and `BlocObserver.onError`, but the state
**doesn't change**, so an uncaught failure means a stuck `Loading` (ERR-010).

```dart
// data/todos_repository.dart
class TodosRepository {
  TodosRepository(this._api);
  final TodosApi _api;

  Future<List<Todo>> fetch() async {
    try {
      return await _api.fetchTodos();
    } on DioException catch (e, st) {
      Error.throwWithStackTrace(mapDio(e, st), st);
    }
  }
}
```

```dart
// bloc/todos_bloc.dart: sealed states (exclusive), Bloc's "Sealed Class and Subclasses"
sealed class TodosState { const TodosState(); }
final class TodosInitial extends TodosState { const TodosInitial(); }
final class TodosLoading extends TodosState { const TodosLoading(); }
final class TodosLoaded extends TodosState { const TodosLoaded(this.todos); final List<Todo> todos; }
final class TodosFailure extends TodosState { const TodosFailure(this.failure); final Failure failure; }

class TodosBloc extends Bloc<TodosEvent, TodosState> {
  TodosBloc(this._repo) : super(const TodosInitial()) {
    on<TodosRequested>(_onRequested);
  }

  final TodosRepository _repo;

  Future<void> _onRequested(TodosRequested event, Emitter<TodosState> emit) async {
    emit(const TodosLoading());
    try {
      emit(TodosLoaded(await _repo.fetch()));
    } on Failure catch (f) {
      emit(TodosFailure(f));
    }
  }
}
```

When old data must stay visible during a failure (Bloc's "Concrete Class and
Status Enum" verdict: "showing a snackbar when an error occurs while still
showing old data"), use a status enum in a Cubit:

```dart
enum TodosStatus { initial, loading, success, failure }

final class TodosListState {
  const TodosListState({this.status = TodosStatus.initial, this.todos = const [], this.failure});
  final TodosStatus status;
  final List<Todo> todos;
  final Failure? failure;

  TodosListState copyWith({TodosStatus? status, List<Todo>? todos, Failure? failure}) =>
      TodosListState(status: status ?? this.status, todos: todos ?? this.todos, failure: failure);
}

class TodosCubit extends Cubit<TodosListState> {
  TodosCubit(this._repo) : super(const TodosListState());
  final TodosRepository _repo;

  Future<void> refresh() async {
    emit(state.copyWith(status: TodosStatus.loading));
    try {
      emit(state.copyWith(status: TodosStatus.success, todos: await _repo.fetch()));
    } on Failure catch (f) {
      emit(state.copyWith(status: TodosStatus.failure, failure: f));   // todos kept
    }
  }
}
```

```dart
// view: BlocListener for the one-time effect, BlocBuilder for rendering
BlocListener<TodosCubit, TodosListState>(
  listenWhen: (prev, curr) => curr.status == TodosStatus.failure && prev.status != TodosStatus.failure,
  listener: (context, state) => ScaffoldMessenger.of(context).showSnackBar(
    SnackBar(content: Text(failureText(AppLocalizations.of(context), state.failure!))),
  ),
  child: BlocBuilder<TodosCubit, TodosListState>(
    builder: (context, state) => switch (state.status) {
      TodosStatus.loading when state.todos.isEmpty => const Center(child: CircularProgressIndicator()),
      TodosStatus.failure when state.todos.isEmpty => ErrorView(
          message: failureText(AppLocalizations.of(context), state.failure!),
          onRetry: context.read<TodosCubit>().refresh,
        ),
      _ => TodoList(todos: state.todos),
    },
  ),
)
```

Bloc review points:
- `emit` inside a stream subscription: use `await emit.forEach(stream,
  onData: ..., onError: (e, st) => TodosFailure(...))` rather than a raw
  `listen`. Calling `emit` after the handler completes asserts.
- Report unexpected errors in one place: `Bloc.observer = AppBlocObserver()`,
  overriding `onError` and forwarding to the crash reporter. Don't also log in
  every bloc (ERR-double-report).
- `addError(e, st)` in a bloc or cubit reports to `onError` without changing
  state. Use it for errors you handled but still want reported.

## 4. Clean Architecture with Either (fpdart)

The Clean Architecture convention with `fpdart` (or `dartz`) is that
repositories and use cases return `Either<Failure, T>` (`Left` = failure).
The rules are the same as for `Result`; only the vocabulary differs. Don't mix
it with a `Result` type in the same codebase.

```dart
// data/repositories/user_repository_impl.dart
class UserRepositoryImpl implements UserRepository {
  UserRepositoryImpl(this._remote);
  final UserRemoteDataSource _remote;

  @override
  Future<Either<Failure, User>> me() async {
    try {
      return Right((await _remote.me()).toEntity());
    } on DioException catch (e, st) {
      return Left(mapDio(e, st));
    } on FormatException catch (e, st) {
      return Left(ParseFailure(cause: e, stackTrace: st));
    }
  }

  // Equivalent with TaskEither:
  TaskEither<Failure, User> meTask() => TaskEither.tryCatch(
        () async => (await _remote.me()).toEntity(),
        (e, st) => e is DioException ? mapDio(e, st) : ParseFailure(cause: e, stackTrace: st),
      );
}
```

```dart
// domain/usecases/get_me.dart
class GetMe {
  const GetMe(this._repo);
  final UserRepository _repo;
  Future<Either<Failure, User>> call() => _repo.me();
}
```

```dart
// presentation (any state solution): fold at the boundary
final result = await getMe();
state = result.fold(ProfileError.new, ProfileLoaded.new);
```

Review points: a use case that unwraps `Either` and *throws* again
(`getOrElse((f) => throw f)`) undoes the whole point (ERR-009). Keep `Left`
values typed, never `Left('message')`.

## 5. Riverpod without MVN (AsyncValue)

`FutureProvider`, `AsyncNotifier` and `StreamProvider` turn a thrown error
into `AsyncError` for you. A repository can throw typed failures, and the
provider is the boundary.

```dart
@riverpod
Future<List<Todo>> todos(Ref ref) => ref.watch(todosRepositoryProvider).fetch(); // throws Failure

@riverpod
class TodoList extends _$TodoList {
  @override
  Future<List<Todo>> build() => ref.watch(todosRepositoryProvider).fetch();

  // Rebuild: while it reloads, AsyncValue keeps the previous value (hasValue stays true),
  // and a failure arrives as AsyncError that still carries that value.
  void refresh() => ref.invalidateSelf();

  Future<void> add(String title) async {
    // A mutation: guard it, so a failure becomes AsyncError instead of escaping to onPressed.
    final result = await AsyncValue.guard(() => ref.read(todosRepositoryProvider).add(title));
    if (result case AsyncError(:final error)) {
      ref.read(snackbarProvider.notifier).show(error);   // or rethrow for the caller's ref.listen
      return;
    }
    ref.invalidateSelf();
  }
}
```

```dart
// view
ref.listen(todoListProvider, (prev, next) {
  if (next case AsyncError(:final error) when prev is! AsyncError) {
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text(failureText(AppLocalizations.of(context), error))),
    );
  }
});

final todos = ref.watch(todoListProvider);
return switch (todos) {
  AsyncData(:final value) => TodoListView(value),
  AsyncError(:final error) when !todos.hasValue => ErrorView(
      message: failureText(AppLocalizations.of(context), error),   // never Text('$error')
      onRetry: () => ref.invalidate(todoListProvider),
    ),
  AsyncError() => TodoListView(todos.value!),            // refresh failed: keep data, the snackbar told them
  AsyncLoading() => const Center(child: CircularProgressIndicator()),
};
```

Riverpod 3 notes (riverpod.dev "What's new"):
- `AsyncValue` is sealed, so `switch` over `AsyncData`/`AsyncError`/`AsyncLoading`
  is exhaustive. `valueOrNull` was renamed to `value`.
- Providers that fail during initialization **retry automatically** with
  exponential backoff. Customize `retry` on the provider or on `ProviderScope`,
  and return `null` to stop. Retries ignore `ProviderException`s.
- Reading a failed provider (`ref.read(p.future)`, `requireValue`) throws a
  `ProviderException` that wraps the original. `AsyncValue.error`,
  `ref.listen(onError:)` and `ProviderObserver`s still get the unwrapped
  error. Catch `on ProviderException catch (e)` and `switch (e.exception)`
  when you must catch around provider reads.
- Mutations expose `MutationIdle`/`MutationPending`/`MutationError`/
  `MutationSuccess`. Render a retry on `MutationError`.

## 6. Provider + ChangeNotifier

```dart
class CartModel extends ChangeNotifier {
  CartModel(this._repo);
  final CartRepository _repo;

  List<Item> _items = const [];
  List<Item> get items => _items;
  bool _loading = false;
  bool get loading => _loading;
  Failure? _failure;
  Failure? get failure => _failure;

  Future<void> load() async {
    _loading = true;
    _failure = null;
    notifyListeners();
    try {
      _items = await _repo.items();
    } on Failure catch (f) {
      _failure = f;
    } finally {
      _loading = false;          // every path leaves loading (ERR-010)
      notifyListeners();
    }
  }
}
```

The view renders with `context.watch<CartModel>()`. One-time effects use a
listener in a `StatefulWidget`, as in MVVM: `addListener` in `initState` and
`removeListener` in `dispose`. Consume the failure after showing it (for
example with a `consumeFailure()` method). Prefer a sealed state class over
the three fields (`AP-boolean-soup-state`) once screens grow.

## 7. GetX

```dart
class TodoController extends GetxController with StateMixin<List<Todo>> {
  TodoController(this._repo);
  final TodoRepository _repo;

  @override
  void onInit() {
    super.onInit();
    load();
  }

  Future<void> load() async {
    change(null, status: RxStatus.loading());
    try {
      final todos = await _repo.fetch();
      change(todos, status: todos.isEmpty ? RxStatus.empty() : RxStatus.success());
    } on Failure catch (f) {
      change(null, status: RxStatus.error(failureKey(f).tr));  // failure -> translation key, never e.toString()
    }
  }
}
```

```dart
// view
controller.obx(
  (todos) => TodoList(todos: todos!),
  onLoading: const Center(child: CircularProgressIndicator()),
  onEmpty: const EmptyView(),
  onError: (message) => ErrorView(message: message ?? 'error_generic'.tr, onRetry: controller.load),
);
```

For a one-time snackbar, use a worker: `ever(failure, (f) => Get.snackbar(...))`
on an `Rx<Failure?>`, registered in `onInit`. Don't call `Get.snackbar` from
`build`.

## 8. setState

```dart
Future<void> _load() async {
  setState(() { _loading = true; _failure = null; });
  try {
    final data = await widget.repository.fetch();
    if (!mounted) return;
    setState(() { _data = data; _loading = false; });
  } on Failure catch (f) {
    if (!mounted) return;
    setState(() { _failure = f; _loading = false; });
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(failureText(AppLocalizations.of(context), f))));
  }
}
```

Check `mounted` after every `await` before calling `setState` or using
`context` (`flutter-ui-practices`, `UI-context-after-await`).

## Cross-cutting

- **Keep data on a refresh failure.** Show the error inline (snackbar or
  banner) and keep the list. Use a full-screen error only when there is
  nothing to show (ERR-error-replaces-data).
- **Retry.** Every error view gets a retry that re-runs the *same* action:
  `ref.invalidate`, `notifier.load`, `bloc.add`, `command.execute`. See
  `references/result-vs-exceptions.md` for automatic retry rules.
- **Log once.** Report unexpected failures in one place: the logic boundary's
  generic catch, `BlocObserver.onError`, a `ProviderObserver`, or the global
  handler. Expected failures (offline, 404) usually aren't crash reports at
  all.
- **Unauthorized.** A 401 mapped to `UnauthorizedFailure` usually triggers a
  global effect (sign out, go to login). Handle it in one auth listener, not in
  every screen.
