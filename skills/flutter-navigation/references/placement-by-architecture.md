# Navigation placement by architecture

## Contents

- [The rule every pattern shares](#the-rule-every-pattern-shares)
- [MVN (Model-View-Notifier, Riverpod)](#mvn-model-view-notifier-riverpod)
- [Plain Riverpod](#plain-riverpod)
- [MVVM (Flutter architecture guide)](#mvvm-flutter-architecture-guide)
- [Bloc / Cubit](#bloc--cubit)
- [Provider / ChangeNotifier](#provider--changenotifier)
- [GetX](#getx)
- [MVC and setState](#mvc-and-setstate)
- [auto_route](#auto_route)
- [Testing the guard](#testing-the-guard)

Examples use Dart 3 and go_router 14+ (`state.uri`, `pathParameters`,
`StatefulShellRoute`). Imports follow the project. Flutter 3.44+ apps on
go_router 18 may import `package:material_ui/material_ui.dart` instead of
`package:flutter/material.dart`.

## The rule every pattern shares

Logic classes (notifiers, view models, blocs) say **what happened**: signed
out, order paid, item deleted. Navigation is decided in exactly two places:

1. **The router**, for rules that hold on *every* navigation: auth,
   onboarding, feature flags, "an admin route needs an admin". It runs for
   deep links, browser Back and `go()` alike, so nothing can skip it.
2. **The view**, for one-time reactions to an outcome ("payment succeeded →
   receipt"). The view listens to state and navigates. It never polls a
   `shouldNavigate` flag (ARCH-111).

So a logic class never holds a `BuildContext`, a `GlobalKey<NavigatorState>`
or a router (ARCH-102, `AP-navigation-in-logic`). The exception is GetX,
where `Get.toNamed` in a controller is the idiom.

The router itself is **composition root** (`lib/app/`, `lib/routing/`,
`lib/core/router/`). It may import repositories, notifiers and views.

## MVN (Model-View-Notifier, Riverpod)

The MVN spec puts one-time side effects in `ref.listen` inside the view's
`build()`, and state in sealed classes. Guards live in the router, which is
a keepAlive provider. It **listens** to the auth notifier and never
**watches** it: a watch would rebuild the provider, create a new `GoRouter`
and reset the stack on every sign-in (NAV-008).

```dart
// lib/core/router/app_router.dart  (composition root)
part 'app_router.g.dart';

@Riverpod(keepAlive: true)
GoRouter appRouter(Ref ref) {
  // Bridge: notify the router when auth changes, without rebuilding it.
  final refresh = ValueNotifier<AuthState>(ref.read(authNotifierProvider));
  ref.listen(authNotifierProvider, (_, next) => refresh.value = next);
  ref.onDispose(refresh.dispose);

  final router = GoRouter(
    initialLocation: Routes.home,
    debugLogDiagnostics: kDebugMode,
    refreshListenable: refresh,
    redirect: (context, state) {
      final atLogin = state.matchedLocation == Routes.login;
      return switch (ref.read(authNotifierProvider)) {
        AuthUnknown() => Routes.splash,                    // still restoring the session
        AuthSignedOut() => atLogin ? null : Routes.loginFrom(state.matchedLocation),
        AuthSignedIn() when atLogin => Routes.home,
        AuthSignedIn() => null,
      };
    },
    errorBuilder: (context, state) => const NotFoundView(),
    routes: $appRoutes,                                    // or a GoRoute list
  );
  ref.onDispose(router.dispose);
  return router;
}
```

With riverpod_generator 3, the provider for `class AuthNotifier` is named
`authProvider`. Use whichever name the project's generator produces.

```dart
// lib/main.dart
class App extends ConsumerWidget {
  const App({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) =>
      MaterialApp.router(routerConfig: ref.watch(appRouterProvider));
}
```

One-time navigation lives in the view:

```dart
// lib/features/checkout/presentation/view/checkout_view.dart
class CheckoutView extends ConsumerWidget {
  const CheckoutView({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    ref.listen(checkoutNotifierProvider, (previous, next) {
      if (next case CheckoutPaid(:final orderId)) {
        context.go(Routes.receipt(orderId));
      }
    });
    final state = ref.watch(checkoutNotifierProvider);
    return switch (state) { /* render each sealed state */ };
  }
}
```

**Sign-out.** The notifier calls the sign-out use case, then sets
`AuthSignedOut()`. The redirect moves the user. Make per-user providers
depend on the session, so they reset by themselves:

```dart
@riverpod
class AuthNotifier extends _$AuthNotifier {
  @override
  AuthState build() => const AuthUnknown();

  Future<void> signOut() async {
    await ref.read(signOutUseCaseProvider)();             // clears tokens in the data layer
    state = const AuthSignedOut();
  }
}

@riverpod
Future<List<Order>> orders(Ref ref) {
  final auth = ref.watch(authNotifierProvider);           // rebuilt (emptied) on sign-out
  if (auth is! AuthSignedIn) return Future.value(const []);
  return ref.watch(getOrdersUseCaseProvider)();
}
```

**Don't flag (MVN):** `ref.listen` → `context.go` in a view, the router
provider importing notifiers (composition root), or `ref.read` inside
`redirect`.

## Plain Riverpod

This is the same as MVN, without the use-case layer. Auth is often an
`AsyncNotifier`. Match on `AsyncValue` so loading and error have a
destination:

```dart
redirect: (context, state) {
  final atLogin = state.matchedLocation == Routes.login;
  return switch (ref.read(authProvider)) {
    AsyncData(value: final user?) => atLogin ? Routes.home : null,
    AsyncData() || AsyncError() => atLogin ? null : Routes.login,
    _ => Routes.splash,                                  // AsyncLoading
  };
},
```

`ref.invalidate(sessionProvider)` on sign-out (or make dependants watch it)
clears cached per-user data.

## MVVM (Flutter architecture guide)

The Flutter architecture guide recommends go_router for navigation, and the
Compass app is its reference. The auth repository is a `ChangeNotifier`
and doubles as `refreshListenable`. View models are built in the route
builders, and views navigate when a `Command` completes.

```dart
// lib/routing/router.dart
GoRouter router(AuthRepository authRepository) => GoRouter(
  initialLocation: Routes.home,
  debugLogDiagnostics: kDebugMode,
  refreshListenable: authRepository,
  redirect: (context, state) async {
    final loggedIn = await context.read<AuthRepository>().isAuthenticated; // cached after first read
    final loggingIn = state.matchedLocation == Routes.login;
    if (!loggedIn) return Routes.login;
    if (loggingIn) return Routes.home;
    return null;
  },
  routes: [/* GoRoute(path: Routes.login, builder: ... LoginViewModel(authRepository: context.read())) */],
);
```

Create it **once**. Compass calls `router(context.read())` inside `build()`,
which NAV-008 flags (hot reload, or any rebuild, resets the location). Hold
it in a `State` instead:

```dart
class _MainAppState extends State<MainApp> {
  late final GoRouter _router = router(context.read<AuthRepository>());

  @override
  void dispose() {
    _router.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => MaterialApp.router(routerConfig: _router);
}
```

The view reacts to the command, and the view model never navigates:

```dart
@override
void initState() {
  super.initState();
  widget.viewModel.login.addListener(_onResult);
}

void _onResult() {
  if (widget.viewModel.login.completed) {
    widget.viewModel.login.clearResult();
    context.go(Routes.home);
  }
}

@override
void dispose() {
  widget.viewModel.login.removeListener(_onResult);
  super.dispose();
}
```

**Sign-out:** `LogoutViewModel.logout` calls the repository and clears
per-user repositories (Compass resets the itinerary config). The repository
notifies, and the redirect sends the user to `/login`.

## Bloc / Cubit

bloclibrary.dev puts one-time effects in `BlocListener`, and blocs never
know about navigation. Expose the auth bloc's stream as a `Listenable` for
the router:

```dart
// lib/app/router.dart
final class StreamListenable extends ChangeNotifier {
  StreamListenable(Stream<Object?> stream) {
    _subscription = stream.listen((_) => notifyListeners());
  }
  late final StreamSubscription<Object?> _subscription;

  @override
  void dispose() {
    _subscription.cancel();
    super.dispose();
  }
}

GoRouter buildRouter(AuthBloc auth, Listenable refresh) => GoRouter(
  refreshListenable: refresh,
  redirect: (context, state) {
    final atLogin = state.matchedLocation == Routes.login;
    return switch (auth.state) {
      AuthAuthenticated() => atLogin ? Routes.home : null,
      AuthUnauthenticated() => atLogin ? null : Routes.login,
      AuthUnknown() => Routes.splash,
    };
  },
  routes: appRoutes,
);
```

```dart
class _AppState extends State<App> {
  late final _auth = AuthBloc(authRepository: widget.authRepository)
    ..add(const AuthSubscriptionRequested());
  late final _refresh = StreamListenable(_auth.stream);
  late final _router = buildRouter(_auth, _refresh);

  @override
  void dispose() {
    _router.dispose();
    _refresh.dispose();
    _auth.close();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) =>
      BlocProvider.value(value: _auth, child: MaterialApp.router(routerConfig: _router));
}
```

One-time navigation:

```dart
BlocListener<CheckoutBloc, CheckoutState>(
  listenWhen: (previous, current) => previous.status != current.status,
  listener: (context, state) {
    if (state.status == CheckoutStatus.paid) context.go(Routes.receipt(state.orderId!));
  },
  child: const CheckoutForm(),
)
```

With plain `Navigator` (the bloclibrary `flutter_login` example), a
`BlocListener<AuthenticationBloc, …>` in `MaterialApp.builder` calls
`navigator.pushAndRemoveUntil(HomePage.route(), (_) => false)`. That
`(_) => false` is what clears the stack on sign-out.

**Don't flag (Bloc):** `BlocListener` → `context.go`. Do flag a bloc that
takes a `BuildContext` or a navigator key (ARCH-102).

## Provider / ChangeNotifier

The auth model is a `ChangeNotifier` above `MaterialApp.router`, and is
passed as `refreshListenable` (the flutter/samples `navigation_and_routing`
app does this):

```dart
class _BookstoreState extends State<Bookstore> {
  final auth = BookstoreAuth();
  late final GoRouter _router = GoRouter(
    refreshListenable: auth,
    redirect: (context, state) {
      final signedIn = auth.signedIn;
      final atSignIn = state.matchedLocation == Routes.signIn;
      if (!signedIn) return atSignIn ? null : Routes.signIn;
      return atSignIn ? Routes.home : null;
    },
    routes: appRoutes,
  );

  @override
  Widget build(BuildContext context) => BookstoreAuthScope(
        notifier: auth,
        child: MaterialApp.router(routerConfig: _router),
      );
}
```

That sample builds the `GoRouter` inside `build()`. The `late final` field
above is the fix.

## GetX

`Get.toNamed`, `Get.offNamed` and `Get.offAllNamed` in controllers are the
pattern's idiom, so they aren't flagged (ARCH-102 is relaxed under getx).
Guards go in `GetMiddleware`, not in each controller's `onInit`:

```dart
class AuthMiddleware extends GetMiddleware {
  @override
  RouteSettings? redirect(String? route) {
    final signedIn = Get.find<AuthService>().isSignedIn.value;
    return signedIn ? null : const RouteSettings(name: Routes.LOGIN);
  }
}

GetPage(
  name: Routes.ORDERS,
  page: () => const OrdersView(),
  binding: OrdersBinding(),
  middlewares: [AuthMiddleware()],
),
```

**Sign-out:** `Get.offAllNamed(Routes.LOGIN)` removes every route. Bound
controllers go with them under the default smart management. Services
registered `permanent: true` survive, so clear any per-user data they hold.
Use the generated `Routes.X` constants, not raw strings (NAV-002).

## MVC and setState

The `State` calls the controller, awaits it, checks `mounted`, then
navigates. Guards still belong in the router (`redirect` +
`refreshListenable` on the auth model). With plain `Navigator`, use
`onGenerateRoute` to check auth for named routes, and on sign-out:

```dart
Navigator.of(context).pushNamedAndRemoveUntil(Routes.login, (route) => false);
```

## auto_route

Guards are `AutoRouteGuard`s attached to routes (`guards: [AuthGuard()]`).
Inside `onNavigation(resolver, router)`, call `resolver.next()` when allowed,
or redirect to the sign-in route (`resolver.redirectUntil(...)` in current
versions). Re-evaluate on auth changes with `reevaluateListenable` on the
router config. Placement is the same as above: logic emits state, and the
guard or the view navigates.

## Testing the guard

Test the guard through a real router, with a fake auth source:

```dart
testWidgets('signed-out users are sent to login with the original target', (tester) async {
  final container = ProviderContainer(overrides: [
    authNotifierProvider.overrideWith(() => FakeAuthNotifier(const AuthSignedOut())),
  ]);
  addTearDown(container.dispose);
  final router = container.read(appRouterProvider);

  await tester.pumpWidget(UncontrolledProviderScope(
    container: container,
    child: MaterialApp.router(routerConfig: router),
  ));
  router.go('/orders/42');
  await tester.pumpAndSettle();

  expect(router.state.matchedLocation, Routes.login);
  expect(router.state.uri.queryParameters['from'], '/orders/42');
});
```

For Bloc, pass a `MockAuthBloc` whose `state` and `stream` you control
(`whenListen`). For MVVM, pass a fake `AuthRepository` (a `ChangeNotifier`)
and call `notifyListeners()` to simulate sign-out. The `flutter-testing`
skill has the full patterns.
