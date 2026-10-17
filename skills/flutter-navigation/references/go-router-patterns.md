# go_router patterns

## Contents

- [1. Version-sensitive APIs](#1-version-sensitive-apis)
- [2. One router, created once](#2-one-router-created-once)
- [3. Route constants, names or typed routes](#3-route-constants-names-or-typed-routes)
- [4. Guards: redirect, onEnter, refreshListenable](#4-guards-redirect-onenter-refreshlistenable)
- [5. ShellRoute and StatefulShellRoute](#5-shellroute-and-statefulshellroute)
- [6. Passing arguments and returning results](#6-passing-arguments-and-returning-results)
- [7. go vs push](#7-go-vs-push)
- [8. Error and not-found pages](#8-error-and-not-found-pages)
- [9. Back button, canPop and PopScope](#9-back-button-canpop-and-popscope)
- [10. Web URLs](#10-web-urls)
- [11. Testing routes and deep links](#11-testing-routes-and-deep-links)

go_router's API moves fast, so read the project's `pubspec.lock` before you
use anything below. This file was checked against the go_router 18.1.0 and
go_router_builder 4.5.1 sources and CHANGELOGs (flutter/packages). For
first-time setup (adding the package, `MaterialApp.router`, the URL strategy,
Android/iOS deep-link configuration), defer to the official
`flutter-setup-declarative-routing` recipe if it's installed.

## 1. Version-sensitive APIs

| Since | API | Notes |
|---|---|---|
| 7.0 | `state.pathParameters`, `state.matchedLocation`; `pathParameters:` / `queryParameters:` on `goNamed` | renamed from `params`, `subloc`, `queryParams` |
| 7.1 | `StatefulShellRoute` (`.indexedStack`, `navigationShell.goBranch`) | stateful nested navigation |
| 8.0 | `push` no longer changes the URL | opt back in with `GoRouter.optionURLReflectsImperativeAPIs = true` |
| 10.0 | `state.uri` (`state.uri.queryParameters`) | replaced `state.location` / `state.queryParameters` (`dart fix --apply` migrates) |
| 14.7 | `GoRouter.state` is non-nullable; `canPop` hardened in 14.8.1 | handy in tests |
| 15.0 | **URLs are case-sensitive by default** (`caseSensitive: true`) | `/Home` and `/home` are different routes |
| 16.0 | go_router_builder 3: route classes use a mixin (`with _$Route`); `GoRouteData.go/push/location` | builder ≥4 makes the mixin public: `with $Route` |
| 16.3 | top-level `onEnter` (`Allow`, `Block.stop()`, `Block.then(...)`) | runs before `redirect` |
| 17.0 | shell routes notify the router's observers by default (`notifyRootObserver`) | analytics observers now see tab changes |
| 17.4 | `BlockedInitialNavigationException` | an initial deep link blocked by `onEnter` |
| 17.5 | path-parameter regex constraints (`':id(\\d+)'`), route `metadata` | non-matching segments fall through to the next route |
| 18.0 | needs Flutter 3.44 / Dart 3.12; examples import `material_ui` | |
| builder 4.5 | duplicate-URL detection for typed routes (build warnings; the `duplicate_route_paths` builder option takes `error` or `ignore`) | the checker's NAV-001 covers untyped `GoRoute`s |

## 2. One router, created once

A `GoRouter` owns the navigation stack. A new instance starts again at
`initialLocation` (or the platform's current URL), so build it once:

```dart
// Fine: top-level final (no dependencies)
final appRouter = GoRouter(routes: appRoutes, errorBuilder: (_, _) => const NotFoundView());

// Fine: State field when it needs injected dependencies
class _AppState extends State<App> {
  late final GoRouter _router = buildRouter(context.read<AuthRepository>());
  @override
  void dispose() {
    _router.dispose();
    super.dispose();
  }
  @override
  Widget build(BuildContext context) => MaterialApp.router(routerConfig: _router);
}

// Fine: keepAlive provider that ref.listen()s (never ref.watch()es) changing state
```

```dart
// Bad (NAV-008): a new router on every build() and every hot reload
@override
Widget build(BuildContext context) => MaterialApp.router(routerConfig: GoRouter(routes: appRoutes));
```

For routes that change at runtime (a feature flag, a different tab set on
tablets), use `GoRouter.routingConfig(routingConfig: ValueNotifier<RoutingConfig>(...))`
and update the notifier. Don't recreate the router.

## 3. Route constants, names or typed routes

Pick one style and use it everywhere. The checker's NAV-002 only fires when
an alternative exists.

**Constants** (Compass, Wonderous):

```dart
abstract final class Routes {
  static const home = '/';
  static const login = '/login';
  static const booking = '/booking';
  static const bookingRelative = 'booking';
  static String bookingWithId(int id) => '$booking/$id';
  static String loginFrom(String from) =>
      Uri(path: login, queryParameters: {'from': from}).toString();
}

context.go(Routes.bookingWithId(42));
```

**Names** (`GoRoute(name: 'booking', path: ...)`) with
`context.goNamed('booking', pathParameters: {'id': '$id'})`. Path parameter
values are `String`s.

**Typed routes** (go_router_builder ≥4, `dart run build_runner build`):

```dart
part 'routes.g.dart';

@TypedGoRoute<HomeRoute>(
  path: '/',
  routes: [TypedGoRoute<ProductRoute>(path: r'products/:id(\d+)')],
)
class HomeRoute extends GoRouteData with $HomeRoute {
  const HomeRoute();
  @override
  Widget build(BuildContext context, GoRouterState state) => const HomeView();
}

class ProductRoute extends GoRouteData with $ProductRoute {
  const ProductRoute({required this.id, this.tab});
  final int id;          // path parameter, parsed by generated code
  final String? tab;     // not in the path: an optional query parameter
  @override
  Widget build(BuildContext context, GoRouterState state) => ProductView(id: id, tab: tab);
}

// const ProductRoute(id: 42).go(context);  →  /products/42
// final router = GoRouter(routes: $appRoutes);
```

The generated code parses a required `int` with `int.parse` (only nullable
fields use `tryParse`). So `/products/abc` still throws unless the path is
constrained (`(\d+)`, go_router ≥17.5) or there's an error page. Typed
routes remove typos, not hostile input.

## 4. Guards: redirect, onEnter, refreshListenable

Order on every navigation: **`onEnter`** (if any) → top-level **`redirect`**
→ **route-level `redirect`s**. `redirect` is
`FutureOr<String?> Function(BuildContext, GoRouterState)`. Return a location
to redirect, or `null` to stay. Redirecting to the current location is a
no-op. Chains stop at `redirectLimit` (default 5) and show the error page.

```dart
redirect: (context, state) {
  final signedIn = auth.isSignedIn;                 // in-memory: no I/O here (NAV-007)
  final atLogin = state.matchedLocation == Routes.login;
  if (!signedIn) return atLogin ? null : Routes.loginFrom(state.matchedLocation);
  if (atLogin) return Routes.home;
  return null;
},
refreshListenable: auth,                            // re-run on sign-in/sign-out (NAV-012)
```

- **`refreshListenable`** re-runs the redirect for the *current* location
  when it notifies. Without it, a sign-out leaves the user on a protected
  screen until the next tap. Alternatives: `GoRouter.refresh()`, or reading
  an `InheritedWidget` via `X.of(context)` inside the redirect (that
  registers a dependency, as the docs note).
- **Route-level `redirect`** suits rules that belong to one subtree (an
  admin section, a feature flag). Put app-wide auth at the top level so no
  route can forget it.
- **`onEnter`** (≥16.3) sees `(context, current, next, router)` and returns
  `Allow()`, `Block.stop()` or `Block.then(() => router.go(...))`. It runs
  **once**, against the literal target, before redirects, and never sees
  intermediate redirect hops. Use it for links that shouldn't navigate at
  all: consume a referral or a magic-link token, show a sheet, or reject a
  malformed link. Keep auth in `redirect`, which sees every hop.

```dart
onEnter: (context, current, next, router) {
  if (next.uri.path == '/invite') {
    final code = next.uri.queryParameters['code'];
    if (code == null || !RegExp(r'^[A-Za-z0-9]{8}$').hasMatch(code)) return const Block.stop();
    return Block.then(() => router.go(Routes.inviteConfirm(code)));   // confirm before acting
  }
  return const Allow();
},
```

- **Loops.** Two rules that disagree (onboarding sends to `/login`, auth
  sends back to `/onboarding`), or a target rebuilt from the current URI
  (`/login?from=/login?from=…`), loop until `redirectLimit`. Check "already
  there" first.
- **Async redirects** are allowed, but they run on every navigation. Await
  only cached values (Compass's `isAuthenticated` reads storage once, then
  memory). Restore the session at startup behind a splash route.

## 5. ShellRoute and StatefulShellRoute

- **`ShellRoute`** wraps child routes in persistent UI (an app bar, a rail),
  with one nested `Navigator`. Switching tabs replaces the child, so each
  tab's stack and scroll position are lost.
- **`StatefulShellRoute.indexedStack`** gives each branch its own `Navigator`
  and keeps it alive. That's what bottom-navigation apps usually want.

```dart
StatefulShellRoute.indexedStack(
  builder: (context, state, navigationShell) => ScaffoldWithNavBar(navigationShell: navigationShell),
  branches: [
    StatefulShellBranch(routes: [GoRoute(path: Routes.jobs, builder: (_, _) => const JobsView())]),
    StatefulShellBranch(routes: [GoRoute(path: Routes.account, builder: (_, _) => const AccountView())]),
  ],
)

// in ScaffoldWithNavBar
NavigationBar(
  selectedIndex: navigationShell.currentIndex,
  onDestinationSelected: (index) => navigationShell.goBranch(
    index,
    initialLocation: index == navigationShell.currentIndex,   // re-tap pops the tab to its root
  ),
  destinations: const [/* ... */],
)
```

- Full-screen routes from inside a branch (a dialog-like editor, a login
  wall) take `parentNavigatorKey: rootNavigatorKey`, so they cover the bar.
- `StatefulShellBranch(preload: true)` builds a branch before its first
  visit. Use it only when the tab is cheap.
- After sign-out, the redirect sends the user outside the shell, which
  removes it from the tree and drops every branch stack. Don't keep
  branch-level state in globals.

## 6. Passing arguments and returning results

| Channel | Survives deep link / web refresh / restoration | Use for |
|---|---|---|
| path parameter (`/orders/:id`) | yes | identity: what the screen shows |
| query parameter (`?tab=reviews`) | yes | optional view state: filters, tabs, sort |
| `extra` | **no** (unless an `extraCodec` encodes it, and never across a fresh deep link) | an in-memory optimisation: a preloaded object to avoid a refetch |

```dart
GoRoute(
  path: ':id',
  builder: (context, state) {
    final id = int.tryParse(state.pathParameters['id'] ?? '');
    if (id == null) return const NotFoundView();
    final preloaded = state.extra is Order ? state.extra as Order : null;   // optional, never required
    return OrderView(id: id, preloaded: preloaded);
  },
),
```

Results: `final picked = await context.push<Address>(Routes.addressPicker);`
on one side, and `context.pop(address)` on the other. Check
`context.mounted` before using `context` after the `await`
(`UI-context-after-await` in `flutter-ui-practices`).

## 7. go vs push

- **`go(location)`** is declarative. The stack becomes the matched route
  hierarchy for that URL (`/orders/42` is the orders list with order 42 on
  top). Use it for destinations, and after sign-in or sign-out (it drops
  whatever was pushed).
- **`push(location)`** adds a page on top and can return a result. On the
  web, `push` doesn't update the address bar unless
  `GoRouter.optionURLReflectsImperativeAPIs = true`.
- `pushReplacement` and `replace` swap the top page. Use them for "step 2 of
  a wizard shouldn't come back to step 1".
- Plain `Navigator.push(MaterialPageRoute(...))` inside a go_router app
  bypasses the URL and the guard. Keep it for dialogs, sheets and pickers.

## 8. Error and not-found pages

Give the router exactly one error path:

```dart
GoRouter(
  routes: appRoutes,
  errorBuilder: (context, state) => NotFoundView(location: state.uri.path),  // don't render state.error to users
);
```

`onException: (context, state, router) => router.go(Routes.home)`
supersedes `errorBuilder`/`errorPageBuilder` when you'd rather redirect than
show a page. Malformed parameters are not route-matching errors. Handle them
in the builder (§6), or constrain the path so they never match.

## 9. Back button, canPop and PopScope

- A deep link can open any screen as the **only** page. `context.pop()`
  there has nothing to pop. Use a fallback:

```dart
void goBack(BuildContext context) =>
    context.canPop() ? context.pop() : context.go(Routes.home);
```

- To intercept system Back (unsaved changes, "back always goes home"), use
  `PopScope`. `WillPopScope` and `onPopInvoked` are deprecated, and they
  break Android's predictive back:

```dart
PopScope(
  canPop: false,
  onPopInvokedWithResult: (didPop, result) {
    if (!didPop) context.go(Routes.home);   // Compass booking screen
  },
  child: const BookingBody(),
)
```

- go_router routes system Back to the active branch's navigator inside
  `StatefulShellRoute`. Don't add your own `BackButtonListener` on top.

## 10. Web URLs

- The path URL strategy (no `#`) is set up in `main()`. See the official
  recipe.
- URLs are case-sensitive from go_router 15. Set `caseSensitive: false` on a
  route only when old links need it, because two routes differing by case
  then collide (NAV-001).
- Browser Back and refresh rebuild pages from the URL alone. Any screen
  that needs `extra` breaks on refresh (NAV-004).
- Everything in the URL is visible, shareable and logged (NAV-006).

## 11. Testing routes and deep links

Widget-test the router directly. `router.go` behaves like an incoming link:

```dart
testWidgets('a malformed order id shows not-found instead of crashing', (tester) async {
  final router = buildRouter(FakeAuth(signedIn: true));
  addTearDown(router.dispose);
  await tester.pumpWidget(MaterialApp.router(routerConfig: router));

  router.go('/orders/abc');
  await tester.pumpAndSettle();

  expect(find.byType(NotFoundView), findsOneWidget);
  expect(tester.takeException(), isNull);
});

testWidgets('sign-out from a deep page lands on login with a clean stack', (tester) async {
  final auth = FakeAuth(signedIn: true);
  final router = buildRouter(auth);
  await tester.pumpWidget(MaterialApp.router(routerConfig: router));
  router.go('/orders/42');
  await tester.pumpAndSettle();

  auth.signOut();                         // notifies refreshListenable
  await tester.pumpAndSettle();

  expect(router.state.matchedLocation, Routes.login);
  expect(router.canPop(), isFalse);
});
```

End to end, on a device or emulator:

```bash
# Android: open a link the way another app would
adb shell am start -a android.intent.action.VIEW -c android.intent.category.BROWSABLE \
  -d "https://example.com/orders/abc" com.example.app
adb shell pm get-app-links com.example.app        # Android 12+: is the domain verified?

# iOS simulator
xcrun simctl openurl booted "https://example.com/orders/abc"
```

Try every route with a missing, malformed, very long and percent-encoded
parameter, and with a signed-out user. The `flutter-testing` skill covers
fakes and integration tests.
