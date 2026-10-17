# Anti-patterns: Presentation

Rules for views and the logic classes behind them (view models, notifiers, blocs, controllers): the UI reaching past its logic class into data, logic classes reaching into Flutter UI or navigation, hand-managed subscriptions, and screens or logic classes that have grown too big.

Part of the architecture anti-pattern catalog. The index, [`references/anti-patterns.md`](../anti-patterns.md), holds the severity scale, the profile rules and a table of every ID; read it first.

## Contents

- [ARCH-005 ui-depends-on-data-source](#arch-005-ui-depends-on-data-source)
- [ARCH-006 ui-depends-on-dto](#arch-006-ui-depends-on-dto)
- [ARCH-008 view-depends-on-repository](#arch-008-view-depends-on-repository)
- [ARCH-009 logic-depends-on-flutter-ui](#arch-009-logic-depends-on-flutter-ui)
- [ARCH-101 io-in-widget](#arch-101-io-in-widget)
- [ARCH-102 context-in-logic](#arch-102-context-in-logic)
- [ARCH-103 god-file](#arch-103-god-file)
- [AP-massive-view](#ap-massive-view)
- [AP-god-viewmodel](#ap-god-viewmodel)
- [AP-navigation-in-logic](#ap-navigation-in-logic)
- [AP-stream-subscription-in-widget](#ap-stream-subscription-in-widget)

### ARCH-005 ui-depends-on-data-source

**High** · applies: all · detect: arch_check (import)

**Problem.** A `view`/`widget` file imports a source, service, repository
implementation, or an I/O package (`dio`, `http`, `shared_preferences`,
`cloud_firestore` …).
**Why.** Every pattern agrees the UI doesn't do I/O. The call can't be faked in
widget tests, may re-run on rebuilds, and skips the repository's caching and
error mapping.

```dart
// Bad: presentation/view/profile_view.dart
import 'package:dio/dio.dart';

onPressed: () async {
  final res = await Dio().get('https://api.example.com/me');
  setState(() => _name = res.data['name']);
},
```

```dart
// Good (MVN shown; the same idea in every pattern)
onPressed: ref.read(profileNotifierProvider.notifier).load,
// ProfileNotifier → GetProfile use case → ProfileRepository → ProfileSource (Dio)
```

**Fix.** Move the call into a service/source, wrap it in a repository, and call
it from the pattern's logic class.
**False positives.** The composition root (`main.dart`, `app/`, `di/`) may
construct `Dio`. Widgets that import a package only for a *type* used in a
callback signature are rare, but read before reporting.
**As calibrated (what the checker does).**
- For an I/O package, only uses inside Widget/State class bodies count. A
  provider declared in the same file is logic (riverpod's own examples do this).
- Exception types only (`err is DioException`) are reported **low**: the real
  problem is the repository letting a transport exception reach the UI.
  `CancelToken` and similar values don't count.
- Transport or a source constructed only inside a `create:` argument
  (`BlocProvider(create: (_) => PostBloc(httpClient: http.Client()))`) or a
  `*ViewModel(`/`*Bloc(` constructor call is **low**: "constructed at a DI site;
  see ARCH-007".
- A concrete repository with no contract (role `repository`) is ARCH-008
  (medium, with the BlocProvider/RepositoryProvider exemption), not ARCH-005.
- Under **riverpod** and **provider**, a view that reaches a service or
  repository implementation only through its provider (`ref.read(soundServiceProvider)`)
  is **low**. Constructing the class or calling `X.instance` stays high.
- When ARCH-008 fires on the same import, only ARCH-005 is reported (note
  `also ARCH-008`), unless ARCH-005 was downgraded below it.

### ARCH-006 ui-depends-on-dto

**Medium** · applies: `clean_architecture: true`, or whenever the imported file
is `*_dto.dart`/`*_request.dart`/`*_response.dart` · detect: arch_check (import)

**Problem.** A presentation file imports a DTO.
**Why.** API changes (a renamed JSON field, a nullable that wasn't) break
widgets directly, and UI code ends up handling transport quirks.

```dart
// Bad
import '../../data/models/movie_response.dart';
class MovieTile extends StatelessWidget {
  const MovieTile({super.key, required this.movie});
  final MovieResponse movie;
}
```

```dart
// Good
import '../../domain/entities/movie_entity.dart';
class MovieTile extends StatelessWidget {
  const MovieTile({super.key, required this.movie});
  final MovieEntity movie;
}
```

**Fix.** Map DTOs to entities/domain models in the repository; widgets take
those.
**False positives.** In small layer-first MVVM apps the Flutter team rates
separate API and domain models only "Conditional: large apps". There, a shared
`models/` class used by both API and UI isn't a DTO leak, and the rule won't
fire unless the file has a DTO suffix.

### ARCH-008 view-depends-on-repository

**Medium** · applies: mvvm, mvn, bloc, mvc, getx · doesn't apply: provider,
riverpod, setstate, unknown; Bloc files containing `BlocProvider(`,
`RepositoryProvider(` or `MultiRepositoryProvider(` · detect: arch_check (import)

**Problem.** A view or widget imports a repository (contract or impl) or a use
case.
**Why.** In these patterns the view talks to exactly one logic object. A view
calling a repository splits logic between two places and bypasses the state the
logic class maintains.

```dart
// Bad (MVVM)
import '../../../data/repositories/booking_repository.dart';
onDismissed: (_) => context.read<BookingRepository>().delete(booking.id),
```

```dart
// Good
onDismissed: (_) => viewModel.deleteBooking.execute(booking.id),
```

**Fix.** Route the call through the view's view model / notifier / bloc /
controller.
**False positives.** Bloc pages that construct a bloc with
`context.read<Repo>()` inside `BlocProvider(create:)` are exempt. MVVM route
builders that create view models with repositories are composition root.

### ARCH-009 logic-depends-on-flutter-ui

**Medium** (getx: **Low**) · applies: all · doesn't apply: `foundation.dart`
imports · detect: arch_check (import)

**Problem.** A logic class (view model, notifier, bloc, cubit, controller)
imports `material.dart`, `widgets.dart` or `cupertino.dart`.
**Why.** Logic becomes coupled to widgets and harder to unit-test, and it's a
strong hint that UI decisions (colours, icons, dialogs) are being made in the
wrong layer.

```dart
// Bad
import 'package:flutter/material.dart';
class WeatherCubit extends Cubit<WeatherState> {
  Color get background => state.temp > 30 ? Colors.orange : Colors.blue;
}
```

```dart
// Good
enum TempBand { cold, mild, hot }
class WeatherCubit extends Cubit<WeatherState> {
  TempBand get band => switch (state.temp) { > 30 => TempBand.hot, < 10 => TempBand.cold, _ => TempBand.mild };
}
// the view maps TempBand → Color via Theme
```

**Fix.** Expose semantic values; map them to UI types in the view. Import
`foundation.dart` if you only need `ChangeNotifier` or `@immutable`.
**False positives.** GetX controllers that own `TextEditingController`s import
`widgets.dart` idiomatically (hence Low under getx).

### ARCH-101 io-in-widget

**High** · applies: all · detect: arch_check (regex in widget/State classes)

**Problem.** A widget or `State` class calls `http.get(…)`, `Dio(`,
`dio.get(…)`, `SharedPreferences.getInstance(`, `FirebaseFirestore.instance`,
`openDatabase(` or `jsonDecode(`.
**Why.** I/O in widgets is the textbook smart-UI failure: untestable, repeated
on rebuild or re-mount, errors handled ad hoc or not at all, and no single
source of truth.

```dart
// Bad
class _NewsState extends State<News> {
  @override
  void initState() {
    super.initState();
    http.get(Uri.parse('$base/news')).then((r) =>
        setState(() => _items = (jsonDecode(r.body) as List).cast()));
  }
}
```

```dart
// Good (MVVM)
class NewsScreen extends StatelessWidget {
  const NewsScreen({super.key, required this.viewModel});
  final NewsViewModel viewModel; // load command calls NewsRepository → NewsApiService
  @override
  Widget build(BuildContext context) => ListenableBuilder(
        listenable: viewModel,
        builder: (context, _) => NewsList(items: viewModel.items),
      );
}
```

**Fix.** Same as ARCH-005: service → repository → logic class.
**False positives.** `jsonDecode` of a constant asset string in a demo widget,
or code inside a widget file but outside any widget class. Read before
reporting.

### ARCH-102 context-in-logic

**Medium** · applies: all · doesn't apply: `Get.` navigation/overlays under
getx · detect: arch_check (regex)

**Problem.** A logic class has a `BuildContext` parameter or field, or calls
`Navigator.of(`, `ScaffoldMessenger.of(`, `showDialog(`,
`showModalBottomSheet(`, `context.go(`/`context.push(`.
**Why.** Logic becomes untestable without a widget tree, and a context held
across an `await` may belong to a disposed widget. See
`AP-navigation-in-logic` for each pattern's sanctioned alternative.

```dart
// Bad
class LoginViewModel extends ChangeNotifier {
  Future<void> login(BuildContext context) async {
    await _auth.login(_email, _password);
    Navigator.of(context).pushReplacementNamed('/home');
  }
}
```

```dart
// Good
class LoginViewModel extends ChangeNotifier {
  late final login = Command0(_login); // the view listens and navigates on completed
  Future<Result<void>> _login() => _auth.login(_email, _password);
}
```

**Fix.** Expose the outcome; let the view (or a router redirect) navigate.
**False positives.** Under getx, `Get.toNamed`/`Get.snackbar` in controllers is
idiomatic. A `BuildContext` mentioned only in a doc comment is stripped and
won't fire.

### ARCH-103 god-file

**Medium** · applies: all · detect: arch_check (line count: logic > 400, view/widget > 500, any file > 800)

**Problem.** A non-generated file exceeds its role's size limit. The finding
reports the line count.
**Why.** Size is a proxy for too many responsibilities. Large logic files
mix unrelated state; large widget files mean monolithic `build()` methods with
wide rebuilds.

```dart
// Bad: home_view.dart, 900 lines: header, feed, stories, ads, filters, dialogs
```

```dart
// Good
// home_view.dart          composes: HomeHeader(), StoryStrip(), FeedList(), FilterSheet()
// widget/story_strip.dart (its own ConsumerWidget, watches only storiesProvider)
```

**Fix.** Split by responsibility: extract widgets into classes (not
`_buildX()` helpers), and split logic classes per screen or concern.
**False positives.** Generated code is skipped; large constant tables (themes,
routes, test fixtures, l10n) are long but simple. Report as Info if so.

### AP-massive-view

**High** when the widget does I/O or holds business rules; **Medium** when it's
formatting, validation or data shaping · applies: all · detect: reading
(ARCH-101 and ARCH-005 catch the I/O cases)

**Problem.** A "smart UI": widgets compute prices, filter and sort data,
validate forms, decide flows, format dates and currencies, and hold app state.
**Why.** The Flutter guide's strongest UI rule: a view's only logic is simple
show/hide `if`s, animation, layout from device info, and simple routing. Logic
in widgets can't be unit-tested, is duplicated across screens, and runs on
every rebuild.

```dart
// Bad
Widget build(BuildContext context) {
  final visible = orders.where((o) => o.status != 'cancelled' && o.date.isAfter(cutoff)).toList()
    ..sort((a, b) => b.total.compareTo(a.total));
  final discount = user.isVip && visible.length > 3 ? 0.1 : 0.0;
  return OrderList(orders: visible, discount: discount);
}
```

```dart
// Good
Widget build(BuildContext context) {
  final state = ref.watch(ordersNotifierProvider); // filtering, sorting, discount live in the notifier/use case
  return switch (state) {
    OrdersLoaded(:final orders, :final discount) => OrderList(orders: orders, discount: discount),
    OrdersLoading() => const OrdersSkeleton(),
    OrdersFailed(:final message) => ErrorView(message: message),
  };
}
```

**Fix.** Move data logic to the logic class (or a use case if reused);
keep the view declarative.
**False positives.** Layout decisions from `MediaQuery`, animation curves,
`if (state.items.isEmpty)`, and l10n formatting via `AppLocalizations` belong
in the view. In `setstate` apps, keep the bar proportional to app size.

### AP-god-viewmodel

**Medium** · applies: all (god view model, god notifier, god bloc, god
controller) · detect: reading (ARCH-103 is the size proxy)

**Problem.** One logic class serves several unrelated screens or concerns: a
`HomeViewModel` with profile, feed, settings and notifications state.
**Why.** Every change risks every screen, rebuilds spread to unrelated widgets,
tests need everything faked. MVVM's one-view-one-view-model rule exists to
prevent it.

```dart
// Bad
class AppBloc extends Bloc<AppEvent, AppState> {
  // handles login, cart, search, theme, push notifications ... 40 events
}
```

```dart
// Good
class AuthBloc extends Bloc<AuthEvent, AuthState> { /* ... */ }
class CartBloc extends Bloc<CartEvent, CartState> { /* ... */ }
class ThemeCubit extends Cubit<ThemeMode> { /* ... */ }
// shared data flows through repositories, not a shared bloc
```

**Fix.** Split by view or concern; share data through repositories (or, in
MVN/Riverpod, by watching a smaller provider).
**False positives.** An app-shell logic class that genuinely owns app-wide
state (auth status, theme) may be broad but shallow.

### AP-navigation-in-logic

**Medium** · applies: all · doesn't apply: getx (`Get.to` in controllers is
idiomatic) · detect: reading (ARCH-102 catches `Navigator`/`context.go`)

**Problem.** Logic classes navigate, often through a global navigator key or a
router singleton.
**Why.** Logic couples to routes and the widget tree; tests can't assert "it
navigated" without a tree; navigation fires even if the screen was popped.

The sanctioned ways, per pattern:

| Pattern | Navigate by |
|---|---|
| Flutter MVVM | the view listens to a command (`completed`) or the view model and navigates; or `go_router` `redirect` + `refreshListenable` driven by a repository (Compass does this for auth) |
| MVN / Riverpod | `ref.listen` in the view's `build()`; or a router redirect watching an auth provider |
| Bloc | `BlocListener` in the view |
| GetX | `Get.toNamed` in the controller is accepted |
| MVC (mvc_pattern) | the view's `State` navigates after calling the controller |

```dart
// Bad
final navigatorKey = GlobalKey<NavigatorState>();
class CheckoutNotifier extends _$CheckoutNotifier {
  Future<void> pay() async {
    await ref.read(payProvider)();
    navigatorKey.currentState!.pushNamed('/receipt');
  }
}
```

```dart
// Good
ref.listen(checkoutNotifierProvider, (prev, next) {
  if (next is CheckoutPaid) context.go('/receipt/${next.orderId}');
});
```

**Fix.** Expose the outcome as state; navigate in the view or the router.
**False positives.** A dedicated, injected navigation service with an
interface, used consistently and tested, is a deliberate project choice.

### AP-stream-subscription-in-widget

**High** if the subscription is never cancelled; **Medium** if cancelled but the
widget does logic in the listener · applies: all · detect: reading

**Problem.** A widget calls `.listen()` on a repository or bloc stream in
`initState` and manages the subscription by hand.
**Why.** A forgotten `cancel()` leaks the `State` and calls `setState` after
dispose. Even when cancelled, the business reaction lives in the widget.

```dart
// Bad
@override
void initState() {
  super.initState();
  widget.repo.watchMessages().listen((m) => setState(() => _messages.add(m)));
}
```

```dart
// Good: let the framework own the subscription
StreamBuilder<List<Message>>(stream: viewModel.messages, builder: (context, snap) => /* ... */);
// or BlocBuilder / ref.watch(messagesProvider) (a StreamProvider) / a view model that subscribes
```

**Fix.** Use `StreamBuilder`, `BlocListener`/`BlocBuilder`, a `StreamProvider`,
or move the subscription into the logic class (cancelled in `dispose`/`close`).
**False positives.** A subscription to a *UI* stream (keyboard visibility, an
animation status) stored in a field and cancelled in `dispose()` is fine.
Lifecycle details are in the `flutter-ui-practices` skill.
