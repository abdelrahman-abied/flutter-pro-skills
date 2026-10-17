# Widget, golden and integration tests

Sources: docs.flutter.dev *Testing* (widget tests, finders, integration
tests), the `flutter_test` API docs (`WidgetTester`, `TestFlutterView`,
accessibility guidelines, `matchesGoldenFile`), `package:fake_async`, and the
compass app's `testing/` helpers. For a step-by-step recipe, use the official
`flutter-add-widget-test` / `flutter-add-integration-test` skills if they're
installed. This file is about doing it *well*.

## Contents
1. A test-app wrapper (do this once)
2. Finders: find by meaning
3. Interactions
4. `pump` vs `pumpAndSettle`, and time
5. `fake_async` in unit tests
6. Layout stress: small screens, large text, RTL
7. Accessibility checks
8. Golden tests
9. Integration tests
10. Network images, platform channels, plugins

---

## 1. A test-app wrapper (do this once)

Every view needs what sits above it in the real app: theme, localization
delegates, DI, and sometimes a router. Put that in one helper so each test
states only what is unique to it. The compass app's `testApp(tester, body)`
works this way, and so does the `pumpApp` extension many teams use.

```dart
// test/helpers/pump_app.dart
extension PumpApp on WidgetTester {
  Future<void> pumpApp(
    Widget body, {
    List<Override> overrides = const [], // Riverpod; use BlocProvider.value / Provider.value for others
    Locale locale = const Locale('en'),
  }) {
    return pumpWidget(
      ProviderScope(
        overrides: overrides,
        child: MaterialApp(
          theme: AppTheme.light(),
          locale: locale,
          localizationsDelegates: AppLocalizations.localizationsDelegates,
          supportedLocales: AppLocalizations.supportedLocales,
          home: body,
        ),
      ),
    );
  }
}
```

Inject fakes through the same DI the app uses (`ProviderScope` overrides,
`BlocProvider.value`, `ChangeNotifierProvider.value`, a constructor
parameter). Don't reach into globals or service locators from the test.

---

## 2. Finders: find by meaning

Find what the user perceives. Tests that do survive refactors, and they
double as an accessibility check.

| Prefer | For |
|---|---|
| `find.text('Checkout')`, `find.textContaining('items')` | visible copy (use the l10n string, or pin the locale) |
| `find.bySemanticsLabel('Remove item')` | icon buttons and images; also proves they're labelled |
| `find.byTooltip('Search')` | icon buttons with tooltips |
| `find.byKey(const ValueKey('cart-total'))` | values with no stable text; add the key in `lib/` for the purpose |
| `find.byType(CartBadge)` | your own public widgets |
| `find.widgetWithText(FilledButton, 'Pay')` | a control by its label |
| `find.descendant(of: find.byType(CartRow), matching: find.text('2'))` | scoping inside a list item |

Avoid `find.byWidgetPredicate` on internal fields, positional `.at(n)` and
`.first` on ambiguous finders, and private widget types
(`TEST-implementation-finder`). Use precise matchers: `findsOneWidget`,
`findsNWidgets(3)` and `findsNothing` say more than `findsWidgets`. To check a
property, read the widget:
`expect(tester.widget<FilledButton>(find.byKey(payKey)).onPressed, isNull)` (disabled).

---

## 3. Interactions

```dart
await tester.enterText(find.byKey(const ValueKey('email')), 'ada@example.com');
await tester.tap(find.widgetWithText(FilledButton, 'Sign in'));
await tester.pump();                                   // run the tap's frame
await tester.scrollUntilVisible(find.text('Item 40'), 300,
    scrollable: find.byType(Scrollable).first);        // lazy lists
await tester.drag(find.byType(Dismissible).first, const Offset(-500, 0));
await tester.sendKeyEvent(LogicalKeyboardKey.enter);   // keyboard and TV remotes
```

A tap on a widget that is off screen or covered prints a warning and hits
nothing. Scroll it into view first, or the test passes for the wrong reason.

---

## 4. `pump` vs `pumpAndSettle`, and time

`testWidgets` bodies run on a **fake clock**. Timers and `Future.delayed`
fire only when the test advances time.

| Call | Does | Use for |
|---|---|---|
| `pumpWidget(w)` | builds `w` and renders one frame | the initial tree |
| `pump()` | flushes microtasks, renders one frame | after a tap, or after a fake future completes |
| `pump(d)` | advances the fake clock by `d`, then renders | debounces, fake latencies, animation midpoints |
| `pumpAndSettle()` | pumps until no frame is scheduled (fails after its timeout) | finite transitions: route push, dialog, expansion |
| `runAsync(() => …)` | runs real async work (real timers, real I/O) | image decoding, file I/O, isolates; slow, so use it sparingly |

`pumpAndSettle` never settles while an endless animation is on screen
(`CircularProgressIndicator`, a repeating `AnimationController`, a shimmer).
There, step with `pump()` (`TEST-pump-and-settle-endless`). Don't `await
Future.delayed` in a widget test body to "wait": on the fake clock it doesn't
advance by itself. Use `pump(duration)`.

Typical async view test, with a fake repository that answers after 300 ms:

```dart
await tester.pumpApp(const MovieView(), overrides: [
  movieRepositoryProvider.overrideWithValue(FakeMovieRepository([kMovie])..latency = const Duration(milliseconds: 300)),
]);
await tester.tap(find.text('Fetch Trends'));
await tester.pump();                                      // Loading frame
expect(find.byType(CircularProgressIndicator), findsOneWidget);
await tester.pump(const Duration(milliseconds: 300));    // fake latency elapses
expect(find.text(kMovie.title), findsOneWidget);
```

---

## 5. `fake_async` in unit tests

Plain `test()` bodies run on the real clock. Wrap time-dependent code in
`fakeAsync` and drive it with `elapse` and `flushMicrotasks`. Don't `await`
inside the callback: on the fake clock, nothing completes until you elapse.

```dart
import 'package:fake_async/fake_async.dart';

test('search debounces for 300 ms', () {
  fakeAsync((async) {
    final debouncer = SearchDebouncer(const Duration(milliseconds: 300));
    final queries = <String>[];
    debouncer.queries.listen(queries.add);

    debouncer
      ..add('a')
      ..add('ab');
    async.elapse(const Duration(milliseconds: 299));
    expect(queries, isEmpty);

    async.elapse(const Duration(milliseconds: 1));
    expect(queries, ['ab']);
  });
});
```

`package:clock`'s `clock.now()` follows the fake time inside `fakeAsync`.
Code that calls `DateTime.now()` directly doesn't, so inject a clock
(`TEST-real-clock`). For Bloc, `blocTest(wait: …)` covers debounced
transformers.

---

## 6. Layout stress: small screens, large text, RTL

Overflow errors fail a widget test by default, which makes these checks cheap.

```dart
testWidgets('checkout fits a small phone at 200% text', (tester) async {
  tester.view.physicalSize = const Size(960, 1920); // 320 x 640 logical at 3x
  tester.view.devicePixelRatio = 3.0;
  addTearDown(tester.view.reset);

  await tester.pumpWidget(MaterialApp(
    builder: (context, child) => MediaQuery(
      data: MediaQuery.of(context).copyWith(textScaler: const TextScaler.linear(2.0)),
      child: child!,
    ),
    home: const CheckoutView(),
  ));

  expect(tester.takeException(), isNull); // no RenderFlex overflow
  expect(find.text('Pay'), findsOneWidget);
});
```

For **RTL**, pump with an RTL locale (`locale: const Locale('ar')`, with the
delegates) or wrap the body in `Directionality(textDirection:
TextDirection.rtl, …)`. Then assert positions, not just presence. For example,
check that a leading icon is on the right with
`tester.getTopLeft(find.byIcon(Icons.arrow_back)).dx > 160`. This catches
`EdgeInsets.only(left: …)` and `Alignment.centerLeft` that should be
`EdgeInsetsDirectional` and `AlignmentDirectional` (`UI-rtl` in the
`flutter-ui-practices` skill). Run the same test body for each locale in a
`for` loop.

---

## 7. Accessibility checks

`flutter_test` ships guideline matchers. Turn semantics on for the test:

```dart
testWidgets('cart meets tap-target and label guidelines', (tester) async {
  final handle = tester.ensureSemantics();
  await tester.pumpApp(const CartView());

  await expectLater(tester, meetsGuideline(androidTapTargetGuideline)); // 48x48
  await expectLater(tester, meetsGuideline(iOSTapTargetGuideline));     // 44x44
  await expectLater(tester, meetsGuideline(labeledTapTargetGuideline));
  await expectLater(tester, meetsGuideline(textContrastGuideline));
  handle.dispose();
});
```

---

## 8. Golden tests

A golden compares a rendered widget with a stored PNG:

```dart
@Tags(['golden'])
library;

void main() {
  setUpAll(loadAppFonts); // a helper that loads the app's fonts with FontLoader

  testWidgets('MovieCard golden', (tester) async {
    tester.view.physicalSize = const Size(400, 300);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.reset);

    await tester.pumpApp(const Center(child: MovieCard(movie: kMovie)));
    await expectLater(find.byType(MovieCard), matchesGoldenFile('goldens/movie_card.png'));
  });
}
```

- **Create or update** the images with `flutter test --update-goldens` (or
  `--update-goldens test/goldens/`), then review the image diff in the PR like
  code.
- **Fonts.** By default the test environment renders text in a box font, so
  goldens compare boxes. Load the real fonts (and `MaterialIcons`) with
  `FontLoader` in `setUpAll` if the golden is meant to show typography.
- **Pin the environment.** Rendering differs slightly across operating
  systems. Generate and compare goldens on one OS (usually the CI's Linux or
  macOS image), tag them `golden`, run them in that job only (`--tags golden`),
  and exclude them elsewhere (`--exclude-tags golden`). Declare the tag in
  `dart_test.yaml`.
- **Keep them small and deliberate.** Golden a component in its states
  (default, pressed, disabled, error, RTL, dark), not whole screens that change
  every sprint. A screen golden fails on every copy change and teaches people
  to run `--update-goldens` without looking.
- **Libraries.** `alchemist` adds multi-scenario golden grids and CI-friendly
  rendering. `golden_toolkit` is no longer maintained (check pub.dev before
  adopting it). Plain `matchesGoldenFile` needs neither.
- **Screenshot-only "preview" tests** that save PNGs and assert nothing are
  `TEST-preview-only` (Info). Promote the ones that matter to goldens.

---

## 9. Integration tests

Integration tests run the real app on a device, emulator or desktop. They're
slow and coarse, so keep a **handful** for the flows that must never break
(onboarding, sign-in, purchase, playback), and leave the branches to unit and
widget tests.

```yaml
# pubspec.yaml
dev_dependencies:
  integration_test:
    sdk: flutter
  flutter_test:
    sdk: flutter
```

```dart
// integration_test/checkout_flow_test.dart
void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();

  testWidgets('a user can add an item and check out', (tester) async {
    await tester.pumpWidget(ProviderScope(
      overrides: [paymentGatewayProvider.overrideWithValue(FakePaymentGateway())],
      child: const App(),
    ));
    await tester.pumpAndSettle();

    await tester.tap(find.text('Add to cart'));
    await tester.tap(find.byTooltip('Cart'));
    await tester.pumpAndSettle();
    await tester.tap(find.widgetWithText(FilledButton, 'Pay'));
    await tester.pumpAndSettle();

    expect(find.text('Thank you!'), findsOneWidget);
  });
}
```

- Run them with `flutter test integration_test/` on a connected device or
  desktop, or with `flutter drive` plus a `test_driver/` entry point for the
  web.
- Fake the outside world at the same seams as the widget tests (payment, push,
  analytics). Hit a staging backend only in separately tagged tests.
- Native UI (permission dialogs, notifications, system settings) is outside
  `integration_test`'s reach. `patrol` drives it, if the project uses it.
- The gap script maps only `test/`. It counts `integration_test/` files but
  doesn't credit them to units.

---

## 10. Network images, platform channels, plugins

- **`Image.network`** gets an HTTP 400 in widget tests, because the test
  binding blocks real HTTP. Wrap the pump in `mockNetworkImages(() async {
  … })` from `mocktail_image_network`, as the compass app does, or inject an
  image provider.
- **Plugins and platform channels**: put them behind your own interface (a
  source or service) and fake that. That's the architectural answer. When you
  must test the channel wrapper itself, use
  `TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler(channel, handler)`
  and reset it with `addTearDown`.
- **`SharedPreferences`**: call `SharedPreferences.setMockInitialValues({...})`
  in `setUp`. With `shared_preferences` 2.3+ and its async APIs, follow the
  package's in-memory testing setup.
- **Databases** (drift, sqflite): use an in-memory database in repository tests
  (drift: `NativeDatabase.memory()`; sqflite: `sqflite_common_ffi` with
  `inMemoryDatabasePath`). That tests the real SQL without disk state leaking
  between tests.
