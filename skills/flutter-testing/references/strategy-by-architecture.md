# Test strategy by architecture

Sources: docs.flutter.dev *App architecture › Testing each layer* (the compass
app case study) and the testing items of the architecture recommendations
(Strong: "test architectural components separately, and together" and "make
fakes for testing"), riverpod.dev *Testing your providers*, bloclibrary.dev
*Testing* plus the `bloc_test` README, the MVN spec by its author, and the
`package:test`, `flutter_test`, `mocktail` and `fake_async` docs.

The rule that holds everywhere: **test the class that holds the logic, through
its public API, with its dependencies faked at the nearest seam.** The patterns
differ only in where the logic lives and where the seam is.

## Contents
1. Shared ground: fakes, mocks, layout, the pyramid
2. MVN (Model-View-Notifier with Riverpod)
3. Plain Riverpod (not MVN)
4. MVVM (the Flutter team's guide)
5. Bloc and Cubit
6. Clean Architecture (any presentation pattern)
7. Provider and ChangeNotifier
8. GetX
9. setState-only apps

---

## 1. Shared ground

**Fakes vs mocks.** A *fake* is a small working implementation of a contract
(`FakeTodoRepository implements TodoRepository` backed by a list). A *mock*
(mocktail, mockito) records calls and returns stubbed answers. The Flutter
guide's recommendation is **Strong: make fakes for testing**. A fake tests
behaviour and survives refactors. A mock tests call sequences and breaks
when they change. Use mocks for:

- collaborators you can't fake cheaply (`GoRouter`, platform channels,
  third-party SDKs);
- cases where the interaction *is* the behaviour ("sends exactly one
  analytics event");
- projects that already standardised on them.

```dart
// A fake that can also fail on demand: one class covers success and error paths.
class FakeTodoRepository implements TodoRepository {
  FakeTodoRepository([List<Todo> todos = const []]) : _todos = [...todos];

  final List<Todo> _todos;
  Object? error; // set to make the next call throw

  @override
  Future<List<Todo>> fetchTodos() async {
    if (error case final e?) throw e;
    return List.unmodifiable(_todos);
  }

  @override
  Future<void> add(Todo todo) async => _todos.add(todo);
}
```

mocktail basics, when you do mock: `class MockRepo extends Mock implements
Repo {}`, `when(() => repo.fetch()).thenAnswer((_) async => x)`,
`thenThrow(e)`, `verify(() => repo.save(any())).called(1)`. Call
`registerFallbackValue(FakeTodo())` in `setUpAll` before using `any()` with a
custom type. Never mock the class under test (`TEST-mock-of-sut`).

**Layout.** Mirror `lib/` in `test/` (`lib/features/cart/presentation/notifier/cart_notifier.dart`
→ `test/features/cart/presentation/notifier/cart_notifier_test.dart`). Put
shared fakes in `test/helpers/`, or in a `testing/` package as the compass
app does (`testing/fakes/repositories/`). Keep recorded JSON in
`test/fixtures/`. The gap script finds tests by mirror path, then by name,
then by import and use.

**The pyramid.** Most tests are unit tests of logic, use cases and
repositories. They are fast and need no Flutter binding. Next come widget
tests: one per view state, plus the interactions that matter. A few
integration tests (`integration_test/`) cover the critical flows on a device.
If logic can only be tested by pumping widgets, fix the architecture first
(the `flutter-architecture` skill, or `../flutter-architecture/SKILL.md`).

| Layer | Test type | Fake |
|---|---|---|
| Use case / domain rule | unit (`test`) | repository contract |
| Repository impl | unit | source / API client / DAO (or an in-memory DB) |
| Source / API client | unit | `MockClient` (http), Dio `httpClientAdapter`, recorded fixtures |
| Logic holder (notifier, view model, bloc, controller) | unit | repositories or use cases |
| View | widget (`testWidgets`) | logic holder's dependencies, or a fake logic holder |
| Critical flow | integration | real app, fake or staging backend |

---

## 2. MVN (Model-View-Notifier with Riverpod)

MVN's flow is View → Notifier → UseCase → Repository → Source, and every
binding is a generated provider. That is the seam: **override the repository
provider (or the source provider) and run everything above it for real.** You
don't need to mock the use case or the notifier. The Riverpod docs discourage
mocking notifiers; mock or fake the repository instead.

Order of work:

1. **Use cases** first. They are pure Dart with one `call()`, so construct
   them with a fake repository. Pass-through use cases are covered by step 2.
2. **Notifiers** through a `ProviderContainer` with overrides. Assert every
   sealed state the notifier can emit, including the error mapping.
3. **Repository impls** over a fake source: DTO → entity mapping, error
   mapping, caching.
4. **Views**: `ProviderScope(overrides: …)`, one test per sealed state, and
   the `ref.listen` side effects (snackbar, navigation).

```dart
// test/features/movie/domain/usecases/movie_usecase_test.dart
void main() {
  test('FetchTrendingMovies returns what the repository returns', () async {
    final useCase = FetchTrendingMovies(FakeMovieRepository([kMovie]));
    expect(await useCase(), [kMovie]);
  });
}
```

```dart
// test/features/movie/presentation/notifier/movie_notifier_test.dart
ProviderContainer makeContainer(MovieRepository repository) {
  final container = ProviderContainer(
    overrides: [movieRepositoryProvider.overrideWithValue(repository)],
  );
  addTearDown(container.dispose); // Riverpod 3: ProviderContainer.test(overrides: ...)
  return container;
}

void main() {
  group('MovieNotifier', () {
    test('loadTrending emits Loading then Success', () async {
      final container = makeContainer(FakeMovieRepository([kMovie]));
      final states = <MovieState>[];
      container.listen(movieNotifierProvider, (_, next) => states.add(next),
          fireImmediately: true);

      await container.read(movieNotifierProvider.notifier).loadTrending();

      expect(states, [isA<MovieInitial>(), isA<MovieLoading>(), isA<MovieSuccess>()]);
      expect((states.last as MovieSuccess).movies, [kMovie]);
    });

    test('loadTrending maps a repository failure to MovieError', () async {
      final container = makeContainer(FakeMovieRepository()..error = Exception('offline'));
      final sub = container.listen(movieNotifierProvider, (_, __) {}); // keeps it alive

      await container.read(movieNotifierProvider.notifier).loadTrending();

      expect(sub.read(), isA<MovieError>());
    });
  });
}
```

```dart
// test/features/movie/presentation/view/movie_view_test.dart
testWidgets('MovieView renders the list after Fetch', (tester) async {
  await tester.pumpWidget(ProviderScope(
    overrides: [movieRepositoryProvider.overrideWithValue(FakeMovieRepository([kMovie]))],
    child: const MaterialApp(home: MovieView()),
  ));

  await tester.tap(find.text('Fetch Trends'));
  await tester.pump(); // MovieLoading
  expect(find.byType(CircularProgressIndicator), findsOneWidget);
  await tester.pump(); // the fake completes: MovieSuccess
  expect(find.text(kMovie.title), findsOneWidget);
});
```

Notes:

- **Provider names.** `riverpod_generator` 2.x names `class MovieNotifier`'s
  provider `movieNotifierProvider` (the MVN spec's examples). Newer
  generators drop the `Notifier` suffix (`movieProvider`). Use whatever the
  `.g.dart` file declares.
- **Keep auto-dispose providers alive.** Codegen providers are auto-dispose.
  `container.read` alone can let one be disposed mid-test. Listen first
  (`container.listen(p, (_, __) {})`) and read through the subscription, as
  the Riverpod docs advise.
- **Async providers.** Await `container.read(p.future)` and use
  `expectLater(..., completion(x))` or `throwsA(...)`.
- **Pin a state for a view test** without running logic by overriding the
  notifier with a subclass. Subclass the real notifier rather than
  implementing it, as Riverpod requires:
  `movieNotifierProvider.overrideWith(() => FakeMovieNotifier())`, where
  `class FakeMovieNotifier extends MovieNotifier { @override MovieState build() => const MovieSuccess([kMovie]); }`.
- **Riverpod 3** also offers `tester.container()` in widget tests. It retries
  failed providers automatically, so if an error-state test sees a retry,
  disable retry on the test container or scope (see your version's docs).
- **Inter-notifier links** (`ref.watch(otherProvider)` in `build()`): override
  the other provider with a fixed value to test one notifier in isolation.
  Add one test with both real notifiers to check the link itself.

---

## 3. Plain Riverpod (not MVN)

The same container technique applies. Logic may sit in `Notifier`/`AsyncNotifier`
classes or in functional providers. Test each provider with a
`ProviderContainer`, overriding the providers that do I/O. When a
`FutureProvider` calls an API client provider directly, override the client
provider with a fake. That's the only seam there is.

```dart
test('cartTotalProvider sums the line items', () async {
  final container = ProviderContainer(
    overrides: [cartApiProvider.overrideWithValue(FakeCartApi(lines: [3, 4]))],
  );
  addTearDown(container.dispose);

  await expectLater(container.read(cartTotalProvider.future), completion(7));
});
```

---

## 4. MVVM (the Flutter team's guide)

The guide's own test chapter: view models and views "have well-defined
inputs", so "writing mocks or fakes of the repository is the only setup you
need to do". **View model unit tests don't rely on Flutter libraries.**
Repository tests fake the service (API client) below them. Widget tests reuse
the same fakes, and "view and view model tests only require mocking
repositories if your architecture is sound."

Order: view models (every method and command, success and failure), then
repositories over fake services, then views with the real view model over fake
repositories.

```dart
// test/ui/todo/view_models/todo_view_model_test.dart
void main() {
  group('TodoViewModel', () {
    test('load exposes the todos and notifies once', () async {
      final viewModel = TodoViewModel(todoRepository: FakeTodoRepository([kTodo]));
      var notified = 0;
      viewModel.addListener(() => notified++);

      await viewModel.load();

      expect(viewModel.todos, [kTodo]);
      expect(viewModel.error, isNull);
      expect(notified, 1);
    });

    test('load keeps the old list and exposes the error on failure', () async {
      final repository = FakeTodoRepository([kTodo]);
      final viewModel = TodoViewModel(todoRepository: repository);
      await viewModel.load();

      repository.error = Exception('offline');
      await viewModel.load();

      expect(viewModel.todos, [kTodo]);
      expect(viewModel.error, isA<Exception>());
    });
  });
}
```

```dart
// test/data/repositories/todo_repository_remote_test.dart
test('fetchTodos maps the API payload and drops invalid rows', () async {
  final repository = TodoRepositoryRemote(apiClient: FakeApiClient(todos: kApiTodos));
  final todos = await repository.fetchTodos();
  expect(todos.map((t) => t.id), [1, 2]);
});
```

```dart
// test/ui/todo/widgets/todo_screen_test.dart
testWidgets('TodoScreen lists the todos', (tester) async {
  final viewModel = TodoViewModel(todoRepository: FakeTodoRepository([kTodo]));
  await tester.pumpWidget(MaterialApp(home: TodoScreen(viewModel: viewModel)));
  await viewModel.load();
  await tester.pump();
  expect(find.text(kTodo.title), findsOneWidget);
});
```

With the guide's `Command` objects, test the command's states:
`viewModel.load.running`, `.error`, `.completed` after `await viewModel.load.execute()`.
The compass app also wraps every widget test in a `testApp(...)` helper (theme,
localization delegates, a mocked `GoRouter`). Copy that idea, so each test
only states what is unique to it.

---

## 5. Bloc and Cubit

Bloc "was designed to be extremely easy to test". Use `blocTest` from
`package:bloc_test`. It builds the bloc, runs `act`, collects the emitted
states, closes the bloc, and compares them with `expect`. It also fails if
extra states are emitted. Parameters: `build`, `setUp`, `seed` (start from a
state), `act`, `wait` (for debounce), `skip` (ignore the first N states),
`expect`, `errors`, `verify`, `tearDown`.

State classes need value equality (`Equatable` or `==`). Otherwise, compare
with matchers (`isA<WeatherSuccess>()`).

```dart
// test/weather/cubit/weather_cubit_test.dart
class MockWeatherRepository extends Mock implements WeatherRepository {}

void main() {
  group('WeatherCubit', () {
    late WeatherRepository repository;
    setUp(() => repository = MockWeatherRepository());

    blocTest<WeatherCubit, WeatherState>(
      'emits [loading, success] when the repository returns weather',
      setUp: () => when(() => repository.getWeather('Paris')).thenAnswer((_) async => kWeather),
      build: () => WeatherCubit(repository),
      act: (cubit) => cubit.fetch('Paris'),
      expect: () => [
        const WeatherState(status: WeatherStatus.loading),
        const WeatherState(status: WeatherStatus.success, weather: kWeather),
      ],
    );

    blocTest<WeatherCubit, WeatherState>(
      'emits [loading, failure] when the repository throws',
      setUp: () => when(() => repository.getWeather(any())).thenThrow(Exception('offline')),
      build: () => WeatherCubit(repository),
      act: (cubit) => cubit.fetch('Paris'),
      expect: () => [
        const WeatherState(status: WeatherStatus.loading),
        const WeatherState(status: WeatherStatus.failure),
      ],
    );
  });
}
```

**Views.** Mock the bloc for the *view's* test. That's fine, because the
system under test is the view. Stub the stream with `whenListen`:

```dart
class MockWeatherCubit extends MockCubit<WeatherState> implements WeatherCubit {}

testWidgets('WeatherView shows the temperature on success', (tester) async {
  final cubit = MockWeatherCubit();
  whenListen(cubit, Stream<WeatherState>.empty(),
      initialState: const WeatherState(status: WeatherStatus.success, weather: kWeather));

  await tester.pumpWidget(BlocProvider<WeatherCubit>.value(
    value: cubit,
    child: const MaterialApp(home: WeatherView()),
  ));

  expect(find.text('21 °C'), findsOneWidget);
});
```

Test `BlocListener` side effects by emitting the triggering state through
`whenListen` and asserting the snackbar or route. Don't wire two blocs
together in a unit test. Bloc-to-bloc dependencies are themselves an
anti-pattern (`AP-bloc-to-bloc`).

---

## 6. Clean Architecture (any presentation pattern)

Clean layering adds two cheap, high-value test layers: use cases (domain
rules, pure Dart) and repository impls (mapping and error translation). Test
them under whichever presentation pattern sits on top (sections 2, 4 and 5).

- **Use cases** take a fake of the domain contract. Test every rule and
  guard. Pass-through use cases get covered by the logic tests.
- **Repository impls** take a fake source. Test DTO → entity mapping, error
  mapping (transport exception → domain failure), and caching and
  offline behaviour.
- **DTOs** are parsed from recorded JSON in `test/fixtures/`, including the ugly
  payloads (missing fields, nulls, HTML error pages).
- **Entities** need tests only when they carry logic.

```dart
// test/features/user/data/repositories/user_repository_impl_test.dart
void main() {
  group('UserRepositoryImpl', () {
    test('maps the response to a User entity', () async {
      final repository = UserRepositoryImpl(FakeUserRemoteSource(response: kUserResponse));
      final result = await repository.getUser('42');
      expect(result, isA<Ok<User>>().having((r) => r.value.name, 'name', 'Ada'));
    });

    test('maps a DioException to a NetworkFailure', () async {
      final source = FakeUserRemoteSource()
        ..error = DioException(requestOptions: RequestOptions(path: '/users/42'));
      final result = await UserRepositoryImpl(source).getUser('42');
      expect(result, isA<Error<User>>().having((r) => r.error, 'error', isA<NetworkFailure>()));
    });
  });
}
```

```dart
// test/features/user/data/models/user_response_test.dart
test('UserResponse.fromJson tolerates a missing avatar', () {
  final json = jsonDecode(File('test/fixtures/user_no_avatar.json').readAsStringSync())
      as Map<String, dynamic>;
  expect(UserResponse.fromJson(json).toEntity().avatarUrl, isNull);
});
```

---

## 7. Provider and ChangeNotifier

The `ChangeNotifier` class is the unit. Construct it with fakes and assert its
fields and its notifications. In widget tests, provide the instance you
already hold with `ChangeNotifierProvider.value`. Don't let the widget create
it, or you can't reach it from the test.

```dart
test('Cart.add updates the total and notifies listeners', () {
  final cart = Cart(pricing: FakePricing());
  var notified = 0;
  cart.addListener(() => notified++);

  cart.add(kItem);

  expect(cart.total, kItem.price);
  expect(notified, 1);
});

testWidgets('CartBadge shows the item count', (tester) async {
  final cart = Cart(pricing: FakePricing())..add(kItem);
  await tester.pumpWidget(ChangeNotifierProvider.value(
    value: cart,
    child: const MaterialApp(home: Scaffold(body: CartBadge())),
  ));
  expect(find.text('1'), findsOneWidget);
});
```

---

## 8. GetX

GetX controllers are plain classes. Test them directly and keep the global
container out of it:

- Inject dependencies through the constructor.
- If the code uses `Get.find`, register fakes in `setUp` and call
  `Get.reset()` in `tearDown`, so registrations don't leak between tests
  (`TEST-shared-state`).
- `Get.testMode = true` stops navigation helpers from needing a real app.
- Call `onInit()` yourself when the logic lives there.

```dart
void main() {
  setUp(() => Get.testMode = true);
  tearDown(Get.reset);

  test('CartController.add appends and recomputes the total', () {
    final controller = CartController(FakeCartRepository())..onInit();
    controller.add(kItem);
    expect(controller.items, [kItem]);
    expect(controller.total.value, kItem.price);
  });
}
```

---

## 9. setState-only apps

There is no logic holder to unit-test, so:

- Extract the rules into plain functions or small classes (`priceWithTax`,
  `validateEmail`) and unit-test those.
- Inject the services the `State` uses through the widget's constructor, so a
  widget test can pass fakes.
- Widget-test each screen's states and interactions.

That is proportionate for a small app. When the widget tests start to
duplicate rule checks, it's time to extract a logic class (the
`flutter-architecture` skill's "Choosing a pattern").

```dart
testWidgets('the counter increments on tap', (tester) async {
  await tester.pumpWidget(const MaterialApp(home: CounterPage()));
  await tester.tap(find.byIcon(Icons.add));
  await tester.pump();
  expect(find.text('1'), findsOneWidget);
});
```
