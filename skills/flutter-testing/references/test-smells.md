# Test smells catalog (`TEST-*`)

Every slug this skill reports, with why it matters, a bad and a good example,
and the fix. **(script)** marks the ones `scripts/test_gaps.py` finds. Confirm
each script hit by reading the test before reporting it. The rest need
judgment. Severities are defaults: grade by what the test protects in *this*
code.

## Contents
- Gaps: `TEST-untested-<role>`
- High: `TEST-unawaited-async-expect`
- Medium: `TEST-no-assertion`, `TEST-mock-of-sut`, `TEST-tests-the-mock`, `TEST-mocked-notifier`,
  `TEST-shared-state`, `TEST-real-delay`, `TEST-real-clock`,
  `TEST-real-network`, `TEST-happy-path-only`, `TEST-wrong-layer`,
  `TEST-pump-and-settle-endless`
- Low: `TEST-interaction-only`, `TEST-mock-over-fake`, `TEST-weak-matcher`,
  `TEST-implementation-finder`, `TEST-visible-for-testing`,
  `TEST-golden-unstable`, `TEST-skip-no-reason`, `TEST-giant-file`,
  `TEST-no-teardown`
- Info: `TEST-preview-only`

---

## Gaps

### `TEST-untested-<role>` (script)

Roles and default severities:

- **Medium:** `repository` (roles repository-impl and repository), `usecase`, `logic`.
  A repository impl whose every method is one delegating call with no
  branches is reported **low**, with a "thin delegation" note.
- **Low:** `source`, `service`, `view`
- **Info:** `widget`

**Why.** Untested logic can change silently. The ranking follows the
architecture. Repositories and use cases hold the rules and mappings that
every screen relies on. Logic holders (notifier, view model, bloc) hold the
state machine. Sources and views are next. Small widgets come last.

**How the script decides.** A unit counts as tested when a test:

- mirrors its path (`test/<path>_test.dart`, also under `test/unit/`,
  `test/widget/` or `test/src/`; `lib/src/a/x.dart` also maps to
  `test/a/x_test.dart`), or
- matches its file name anywhere (a trailing `_widget`, `_unit`,
  `_integration` or `_golden` is stripped, so `login_widget_test.dart` tests
  `login.dart`), or
- imports it and uses it: constructs a concrete class, calls a top-level
  function, reads a provider without overriding it, or (for widgets and
  views) refers to the class in a finder.

**What is not a unit.** The script skips these and lists them under
`stats.skipped` with a reason (the text report gives a `not units:` line):

- files of only exception, failure or error types, enums, or value classes
  with no methods (an `Equatable` `NoParams`, a DTO);
- contract-only files, such as an abstract base `UseCase<T, P>`;
- dev stubs and fakes in `lib/` (`AuthRepositoryDev`, `FakeX`, `*Stub`,
  `*Mock`, `*Demo`) and factories or modules that only construct objects
  (`RepositoryFactory`);
- data files that only declare providers (`*_repository_provider.dart`);
- roles `barrel` and `di`, and roles it doesn't know.

ChangeNotifier subclasses (other than `*Repository` and `Command*`) and
`StateNotifier`, `Notifier` and `AsyncNotifier` classes are logic units in
every profile, wherever they live (Provider `*Manager` / `*Model` classes,
immich-style `*.provider.dart`).

The script doesn't scan local `path:` packages (`packages/*/`). The header
lists them with their test-file counts; run the script on each.

Notes on a gap:

- "its provider is overridden with a fake": tests replace this unit, so they
  never run it.
- "likely exercised indirectly through X": a tested unit imports it. Lower
  priority, but a direct test would pin its behaviour.
- "pass-through (no branches)": usually covered by a logic test that runs the
  real use case.

**Fix.** Write the test the strategy table prescribes for the role (SKILL.md
step 2, `references/strategy-by-architecture.md`). Report the top few gaps
in the highest tier, grouped, rather than all 60 widgets.

---

## High

### `TEST-unawaited-async-expect`

**Why.** `expectLater` returns a `Future`. If you don't await it, the test body
can finish, and pass, before the matcher runs. The failure then surfaces in
another test or nowhere. The same happens with `expect(stream, emits…)` on a
stream that hasn't emitted yet when the test ends.

```dart
// Bad: can pass even when the future throws something else
test('rejects an empty cart', () {
  expectLater(checkout(acceptedTerms: true), throwsA(isA<CheckoutException>()));
});

// Good
test('rejects an empty cart', () async {
  await expectLater(checkout(acceptedTerms: true), throwsA(isA<CheckoutException>()));
});
```

**Fix.** Await every `expectLater`, and enable the `unawaited_futures` lint for
`test/`.

---

## Medium

### `TEST-no-assertion` (script)

**Why.** A test with no `expect`/`verify` fails only when something throws.
It passes while the state, the output or the screen is wrong, and it shows up
as coverage. The script counts `expect`, `expectLater`, `verify*`, `fail`,
`check`, `validate*` and drift's `migrateAndValidate` (they throw on a
mismatch), `blocTest`'s `expect:`/`errors:`/`verify:`, golden matchers, and any
helper (in the file or in non-test files under `test/`) whose body asserts
or, for a top-level helper, throws.

```dart
// Bad
test('load', () async {
  await viewModel.load();
});

// Good
test('load exposes the todos', () async {
  await viewModel.load();
  expect(viewModel.todos, [kTodo]);
});
```

**Fix.** Assert the observable result. If the point really is "doesn't throw",
say so: `await expectLater(repo.loadProductDetails(...), completes)`.

### `TEST-mock-of-sut` (script)

**Why.** Mocking or faking the class under test means the test exercises the
stub you wrote, not the code. It always passes. The script flags `class X
extends Mock|Fake|MockBloc|MockCubit implements <SUT>` and
`@GenerateMocks([<SUT>])`, where the SUT is the unit the test file is named
or mirrored after.

```dart
// Bad: cart_repository_impl_test.dart
class MockCartRepositoryImpl extends Mock implements CartRepositoryImpl {}
test('total', () async {
  final repository = MockCartRepositoryImpl();
  when(repository.total).thenAnswer((_) async => 3);
  expect(await repository.total(), 3); // tests mocktail
});

// Good: real SUT, fake dependency
test('total falls back to 0 on a transport error', () async {
  final repository = CartRepositoryImpl(FakeCartApi()..error = DioException(requestOptions: RequestOptions()));
  expect(await repository.total(), 0);
});
```

**Fix.** Construct the real class and fake what it depends on.

### `TEST-tests-the-mock` (script)

**Why.** The test stubs a method on a mock, then calls that same method on the
same mock and asserts what it just stubbed. No production code runs, so the
test can only fail if the mocking library breaks. It usually sits in a
"repository tests" file next to the real impl, which stays untested. The
script flags a test that calls `mock.m()` directly (including inside
`expect(...)`) after `when(() => mock.m())`, when that mock never reaches real
code: it isn't passed to a constructor, a named argument, a list or an
override in that test or in shared setup.

```dart
// Bad
when(() => mockHabitRepository.getAllHabits()).thenAnswer((_) async => [habit]);
final habits = await mockHabitRepository.getAllHabits();
expect(habits, [habit]);

// Good: the real SUT over the mock (or better, a fake)
when(() => mockHaboModel.getAllHabits()).thenAnswer((_) async => [habit]);
final repository = SQLiteHabitRepository(mockHaboModel);
expect(await repository.getAllHabits(), [habit]);
```

**Fix.** Construct the class under test with the mock as its dependency, or
delete the test if a real test already covers the behaviour.

### `TEST-mocked-notifier`

**Why.** The Riverpod docs discourage mocking Notifiers. They only work inside
a provider, and the logic you want to test is in them. Mocking a bloc to test
the bloc has the same problem. Mocking the logic holder is right only in the
*view's* test, to pin a state (subclass the notifier and override `build`; use
`MockBloc` + `whenListen` for Bloc).

**Fix.** Override the repository or source provider and read the real
notifier (strategy-by-architecture.md §2).

### `TEST-shared-state`

**Why.** The following leak state from one test into the next:

- a `ProviderContainer`, bloc or view model created once in `main()` or
  `setUpAll`;
- a GetIt or `Get.put` registration that is never reset;
- a mutable top-level fake.

Tests then pass or fail depending on order, which shows up under
`--test-randomize-ordering-seed random` or when one test is run alone. The
Riverpod docs: "DO NOT share ProviderContainers between tests."

```dart
// Bad
final container = ProviderContainer();
void main() {
  test('a', () { /* mutates */ });
  test('b', () { /* sees a's state */ });
}

// Good
void main() {
  late ProviderContainer container;
  setUp(() {
    container = ProviderContainer(overrides: [/* fakes */]);
    addTearDown(container.dispose);
  });
}
```

**Fix.** Create everything per test in `setUp`. Call `GetIt.I.reset()` or
`Get.reset()` in `tearDown`.

### `TEST-real-delay` (script)

**Why.** `sleep` blocks the isolate, and a real `Future.delayed` waits on the
wall clock. Both make the suite slow, and timing-sensitive assertions flake on
loaded CI runners. The script flags:

- `sleep(...)` inside a test;
- `Future.delayed` with a non-zero duration in a `test()` body outside
  `fakeAsync`;
- `Future.delayed` inside `tester.runAsync` in a widget test.

`testWidgets` bodies already run on a fake clock, and `Duration.zero`,
`.zero`, `Duration()` and literal waits of at most 1 ms are event-loop
flushes, so none of them counts.

```dart
// Bad
n.request('a');
await Future<void>.delayed(const Duration(milliseconds: 80)); // debounce window
expect(env.catalog.calls, [['a']]);

// Good
test('batches requests inside the debounce window', () {
  fakeAsync((async) {
    n.request('a');
    async.elapse(const Duration(milliseconds: 80));
    expect(env.catalog.calls, [['a']]);
  });
});
```

**Fix.** Use `fakeAsync` + `elapse`/`flushMicrotasks` in unit tests,
`tester.pump(duration)` in widget tests, and `wait:` in `blocTest`. If the
code under test uses `Timer`/`Stopwatch` directly, inject a clock or a timer
factory. Some code has to cross a real async boundary (isolates, real I/O).
There, keep the wait minimal, poll with a deadline, and tag the test.

### `TEST-real-clock`

**Why.** Logic that calls `DateTime.now()` or `Timer` directly can't be tested
at a boundary (midnight, expiry, "2 hours ago") without waiting. Its tests
pass or fail by time of day.

```dart
// Bad (lib): String greeting() => DateTime.now().hour < 12 ? 'Morning' : 'Evening';
// Good (lib): String greeting(DateTime now) => now.hour < 12 ? 'Morning' : 'Evening';
test('evening after noon', () => expect(greeting(DateTime(2026, 1, 1, 18)), 'Evening'));
```

**Fix.** Inject `DateTime Function() now` (or a `Clock`), or pass the time in.
Inside `fakeAsync`, `package:clock`'s `clock.now()` follows the fake time.

### `TEST-real-network` (script)

**Why.** A unit test that builds `Dio()`, `http.Client()` or `HttpClient()`
talks to the internet. It's slow, depends on a server, and can hit
production. The script skips:

- files under `real/`, `integration/`, `e2e/` or `live/`;
- files tagged `@Tags(['real' | 'integration' | 'network' | 'live' | 'e2e'])`;
- files that set `httpClientAdapter =`, use `DioAdapter(`, bind a local
  `HttpServer`, or use `HttpOverrides`.

```dart
// Bad
final api = CartApi(Dio());

// Good: package:http
final api = CartApi(MockClient((req) async => http.Response('{"total": 2}', 200)));
// Good: Dio with a fake adapter
final api = CartApi(Dio()..httpClientAdapter = FakeAdapter({'/cart': '{"total": 2}'}));
```

**Fix.** Fake the source above the client, or use a fake adapter or client.
Keep deliberate live tests in `test/real/` with a tag, and exclude them in
`dart_test.yaml`.

### `TEST-happy-path-only`

**Why.** Repositories and logic holders exist largely to handle failure: mapping
transport errors, showing the error state, keeping stale data. A suite that
only feeds success leaves exactly that untested.

**Fix.** For each `catch`/`on`/`Result.error` branch, add a test that makes the
fake fail (`fake.error = …`, `thenThrow`) and asserts the resulting state or
failure type. The `flutter-error-handling` skill (if installed,
`../flutter-error-handling/SKILL.md`) lists the error paths worth covering.

### `TEST-wrong-layer`

**Why.** When business rules can only be reached by pumping a screen or
driving the app, the tests are slow and coarse. One failure can mean ten
different things. It also usually means the logic lives in widgets.

**Fix.** Move the rule into the pattern's logic holder or a use case, unit-test
it there, and keep one widget test that shows the rule's outcome on screen.
Report the structural cause through `flutter-architecture` (`AP-massive-view`).

### `TEST-pump-and-settle-endless`

**Why.** `pumpAndSettle` pumps until no frame is scheduled. An endless
animation (`CircularProgressIndicator`, a repeating controller, a shimmer)
never settles, so the call times out. Even when it does settle, it hides
*which* frame the assertion is about.

```dart
// Bad: the spinner keeps scheduling frames
await tester.tap(find.text('Load'));
await tester.pumpAndSettle();

// Good
await tester.tap(find.text('Load'));
await tester.pump(); // loading frame
expect(find.byType(CircularProgressIndicator), findsOneWidget);
await tester.pump(const Duration(milliseconds: 300)); // the fake's latency
expect(find.text('Done'), findsOneWidget);
```

**Fix.** Use `pump()` / `pump(duration)` to step deliberately. Use
`pumpAndSettle` only for finite transitions (a route push, a dialog opening).

---

## Low

### `TEST-interaction-only`

**Why.** `verify(() => repo.save(any())).called(1)` proves a call happened, not
that the user sees the right thing. When it's the only assertion, a refactor
that keeps the call but breaks the result passes.

**Fix.** Assert the resulting state or output. Keep `verify` for interactions
that *are* the contract (an analytics event, "never calls pay twice").

### `TEST-mock-over-fake`

**Why.** Long `when(...)` chains re-implement the dependency in every test, and
they break when call shapes change. The Flutter guide's recommendation is
Strong: make fakes for testing.

**Fix.** Write one `FakeX implements X` per contract in `test/helpers/`, with
knobs (`error`, seeded data, recorded calls), and reuse it in unit and
widget tests.

### `TEST-weak-matcher`

**Why.** `isNotNull`, `isA<Success>()`, `findsWidgets` and
`greaterThan(0)` pass on wrong data.

```dart
// Bad
expect(state, isA<MovieSuccess>());

// Good
expect(state, isA<MovieSuccess>().having((s) => s.movies, 'movies', [kMovie]));
```

**Fix.** Compare full values (value equality on states pays off here), or add
`.having(...)`. Use `findsOneWidget`/`findsNWidgets(n)`.

### `TEST-implementation-finder`

**Why.** Finding a widget by `byWidgetPredicate` on internal fields, by index
(`.at(3)`), or by a private widget type couples the test to the widget tree.
Harmless refactors then break it, and it says nothing about what the user
sees.

**Fix.** Find by text, `find.bySemanticsLabel` (doubles as an accessibility
check), `find.byTooltip`, or a `ValueKey` you add for the purpose. Scope with
`find.descendant(of: …, matching: …)`.

### `TEST-visible-for-testing`

**Why.** A test that reaches into `@visibleForTesting` members tests the
implementation, and the annotation often marks a unit that is too big to test
through its API.

**Fix.** Test through the public API. If that's impractical, extract the inner
piece into its own class with its own API and tests.

### `TEST-golden-unstable`

**Why.** Golden images differ across operating systems (font rasterisation),
fonts (the test default renders text as boxes unless real fonts are loaded),
surface sizes and pixel ratios. Unpinned goldens fail on another machine, or
compare boxes.

**Fix.** Load the app fonts, fix `tester.view.physicalSize` and
`devicePixelRatio`, run goldens on one OS in CI (tag them `golden`), and
regenerate them with `flutter test --update-goldens`. Details are in
`references/widget-and-golden.md`.

### `TEST-skip-no-reason` (script)

**Why.** `skip: true` or `@Skip()` hides a test with no record of why or when to
bring it back, so it rots. A `skip:` that takes a string prints the reason in
every run. `blocTest`'s `skip: 1` is a state count, not a skip, and isn't
flagged.

**Fix.** `skip: 'flaky on CI until #123 (timer race in SearchNotifier)'`, or fix
the test.

### `TEST-giant-file` (script)

**Why.** A test file over 800 lines usually covers several units. Failures are
hard to place, `setUp` grows to serve every group, and the gap script's
mirror and name mapping can't tell which unit it covers.

**Fix.** Split it into one file per unit or behaviour. Move shared builders and
fakes to `test/helpers/`.

### `TEST-no-teardown`

**Why.** Each of these leaks into later tests or trips the leak checks:

- a `ProviderContainer` that is never disposed;
- a `StreamController` that is never closed;
- a `tester.view.physicalSize` override that is never reset.

**Fix.** Dispose right where you create:
`addTearDown(container.dispose)`, `addTearDown(controller.close)`,
`addTearDown(tester.view.reset)`.

---

## Info

### `TEST-preview-only` (script)

**Why.** Some tests render a widget and save a PNG (`toImage`, `toByteData`,
`writeAsBytes`, or a helper that does) for a human to look at, and assert
nothing. They're useful for design review, but they catch no regression
unless someone opens the images.

**Fix.** Keep them if the team uses them, and report them once, as Info. To
make them guard regressions, turn the important ones into goldens
(`await expectLater(find.byType(MyWidget), matchesGoldenFile('goldens/my_widget.png'))`).
