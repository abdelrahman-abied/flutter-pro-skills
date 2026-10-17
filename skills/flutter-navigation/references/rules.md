# NAV-0xx checker rules

## Contents

- [How the checker reads a project](#how-the-checker-reads-a-project)
- [NAV-001 duplicate-route-path](#nav-001-duplicate-route-path)
- [NAV-002 raw-path-string](#nav-002-raw-path-string)
- [NAV-003 unvalidated-route-param](#nav-003-unvalidated-route-param)
- [NAV-004 extra-hard-cast](#nav-004-extra-hard-cast)
- [NAV-005 untrusted-url-launch](#nav-005-untrusted-url-launch)
- [NAV-006 sensitive-data-in-route](#nav-006-sensitive-data-in-route)
- [NAV-007 io-in-redirect](#nav-007-io-in-redirect)
- [NAV-008 router-recreated](#nav-008-router-recreated)
- [NAV-009 multiple-routers](#nav-009-multiple-routers)
- [NAV-010 missing-auth-guard](#nav-010-missing-auth-guard)
- [NAV-011 debug-log-diagnostics-in-release](#nav-011-debug-log-diagnostics-in-release)
- [NAV-012 redirect-without-refresh](#nav-012-redirect-without-refresh)
- [Calibration](#calibration)

`scripts/check_navigation.py` is static and read-only, uses only the
standard library, and needs no `pub get`. Every hit is a **candidate**. Read
the code before you report it as `confirmed`.

## How the checker reads a project

- It scans `lib/**.dart`, skipping generated files (`*.g.dart`,
  `*.freezed.dart`, …), with comments removed and string contents masked.
- **Route table:** every `GoRoute(...)` call, and calls of classes that
  `extends GoRoute` (Wonderous's `AppRoute('path', ...)`). `path:` values
  are resolved through string constants anywhere in `lib/`
  (`static const x = '...'`, `static String x = '...'`, `$interpolation`),
  and children are joined to their enclosing `GoRoute`. ShellRoutes add no
  segment. Paths the checker can't resolve are counted as `unresolved` and
  skipped.
- **Typed routes:** `@TypedGoRoute` / `TypedRelativeGoRoute` `path:` values.
- **Guards:** `redirect:` / `onEnter:` arguments of `GoRouter`,
  `RoutingConfig`, `GoRoute` and shell routes (inline closures, or named
  functions resolved by name), plus `redirect(BuildContext …)` overrides in
  `GoRouteData` classes.
- **Profile and roles:** from `../flutter-architecture/scripts/arch_check.py
  --json` when installed, otherwise from the pubspec and folder names. The
  profile picks the fix hint for NAV-010 and NAV-012, and turns NAV-010 off
  for getx.
- **Scopes:** "the same function" means the innermost block body or arrow
  expression, so a guard in one route builder doesn't excuse another.

## NAV-001 duplicate-route-path

**Medium** · go_router · detect: resolved full paths compared after
normalising parameter names (`:id` = `:pid`). A regex constraint still
counts, and `caseSensitive: false` compares lowercased.

**Why.** go_router matches the first route. The second is dead code, and
links meant for it open the first page.
**Fix.** Rename, merge, or nest the routes.
**Not flagged.** Routes in different `GoRouter`/`RoutingConfig` calls (for
example, a loading config and the real one). Alternatives in
collection-`if`/`else` branches. Typed routes (go_router_builder ≥4.5 warns
at build time).

## NAV-002 raw-path-string

**Low** · all profiles · detect: `context|router.go/push/pushReplacement/replace('/…')`,
`Navigator.pushNamed(context, '/…')` and friends, `Get.toNamed('/…')`.
Fires only when the project offers an alternative:
- ≥2 route constants (string constants starting with `/` in a
  `Routes`/`Paths`/`…Route…` class)
- typed routes
- a **named** route whose pattern matches the literal

When there are routers in several files, only typed or named routes in the
same file count.

**Why.** A typo or a renamed route compiles and fails at runtime, often only
on the path a test didn't cover.
**Fix.** The note names the constant when the literal equals one
(`use Routes.home`), or the route name (`goNamed('home')`).
**Not flagged.** Projects that consistently use raw strings and have no
constants (FluffyChat). Literals in route definitions and redirect return
values.

## NAV-003 unvalidated-route-param

**Medium**, or **Low** for redirect targets · all profiles · detect, per
function scope:
- `int|double|num|BigInt|DateTime.parse(...)` or `.values.byName(...)` whose
  argument reads `pathParameters[`/`queryParameters[`/`pathSegments[`, or a
  local assigned from one
- `queryParameters['x']!` and `queryParameters['x'] as String`
- `pathSegments[n]` with no `pathSegments.length`/`isEmpty`/`isNotEmpty`/`elementAtOrNull`
  in the scope
- `go/push/replace(x)` where `x` comes from `queryParameters[` with no
  `startsWith('/')`/validate/sanitize check (low)

**Why.** A malformed link throws inside the route builder or redirect. The
user gets an error screen, or a crash in the redirect. An unchecked
`from=` sends the user wherever the link author chose.
**Fix.** `tryParse` / `asNameMap()[raw]` with a not-found page, a path
constraint (`':id(\\d+)'`, go_router ≥17.5), or `safeReturnTo`
(`deep-links-and-security.md` §5).
**Not flagged.** `int.parse` of a parameter whose path declares a regex
constraint (`:id(\d+)`). `state.pathParameters['id']!` alone (a matched
route always has it).
**Known gaps.** Parsing a parameter after it crosses into a widget field
(`int.parse(widget.id)`), and the parsing inside go_router_builder's
generated code (required `int` fields use `int.parse`). Constrain typed
paths instead.

## NAV-004 extra-hard-cast

**Medium** · files using go_router (`extra`), or `settings.arguments` with
Navigator 1 · detect: `.extra as T` (T non-nullable, not
`dynamic`/`Object`), `.extra!`, `settings.arguments as T`, with no
`extra is`, `== null`, `!= null`, `??` or `case` check in the same function.

**Why.** `extra` isn't in the URL. Deep links, web refresh/Back and
restoration arrive without it (or undecoded without an `extraCodec`), so
the cast throws.
**Fix.** Put the id in the path and load the object. Keep `extra` as an
optional preload.
**Not flagged.** `state.extra as Foo?`, or `state.extra is Foo ? state.extra as Foo : null`.

## NAV-005 untrusted-url-launch

**Medium** · all profiles · detect: `launchUrl`/`launchUrlString` (and the
deprecated `launch` when url_launcher is imported) whose URL argument, or a
local it was built from, reads a route parameter, `state.uri`, `extra`,
`href`, `payload`, `message.data`, `notification.data`, a controller's
`.text`, or an initial or streamed app link. Not reported when the
function checks `.scheme`, `isScheme(`, `.host`, an
`allowed…`/`allowList…`/`trusted…` set, or `startsWith('https:`.

**Why.** The OS opens whatever scheme it's given (`intent:`, `javascript:`,
`file:`, other apps' schemes).
**Fix.** `launchTrusted` (`deep-links-and-security.md` §6).
**Known gaps.** A URL passed through a helper's field or parameter (for
example, a `UrlLauncher(context, url)` class). A scheme check that exists
but doesn't block (FluffyChat checks `http`/`https` and then launches every
other scheme anyway). Read launcher helpers by hand.

## NAV-006 sensitive-data-in-route

**High** for secrets (`password`, `accessToken`, `refreshToken`, `jwt`,
`secret`, `apiKey`, `cvv`, `cardNumber`, `ssn`, …). **Medium** for one-time
tokens (`token`, `otp`, `pin`, `sessionId`, …) and PII (`email`, `phone`,
`nationalId`, `iban`, `dob`, …). Detect:
- path templates declaring such a parameter (`/reset/:token`)
- typed-route fields with such names (they become path or query parameters)
- navigation calls whose location interpolates such an identifier
  (`'/session/$accessToken'`, `'${user.email}'`) or a literal `?email=`
- `queryParameters:`/`pathParameters:` maps with such keys

**Why.** Locations are kept in history, logs, analytics and breadcrumbs.
**Fix.** Pass the value in memory. For inbound one-time links, consume the
token in `onEnter`/`redirect` and `go()` to a clean location.
**Not flagged.** Values in `extra:` or `arguments:` (in memory, though see
NAV-004). OAuth/OIDC URLs built for an external browser aren't app
navigation.

## NAV-007 io-in-redirect

**Medium** · go_router · detect, inside a `redirect`/`onEnter` body (inline
or resolved by name): `SharedPreferences.getInstance(`,
`SharedPreferencesAsync(`, `FlutterSecureStorage(`, `.read(key:`, `http.get/post/…(`,
`Dio(`, `dio.get/post/…`, `FirebaseFirestore.instance`, `.collection(`,
`getIdToken(`, `openDatabase(`, `Hive.openBox`, `currentUser.reload(`, and
`await ….fetch*/refresh*/sync*/request*/verify*/validate*(`.

**Why.** Redirects run on every navigation and on every refresh. I/O adds
latency to each tap, races with fast taps, and turns a storage or network
failure into a routing error.
**Fix.** Restore the session once at startup (behind a splash route), keep
the result in memory, and notify `refreshListenable` when it changes.
**Not flagged.** Awaiting a cached getter
(`await authRepository.isAuthenticated` in Compass), or
`ref.read(x.future)` of a provider that has already resolved.

## NAV-008 router-recreated

**Medium** · all profiles · detect:
- `GoRouter(` / `GoRouter.routingConfig(` inside the `build()` of a widget or
  `State` class
- a call, inside such a `build()`, to a function declared as returning
  `GoRouter` (Compass's `router(context.read())`)
- a `GoRouter` built inside a Riverpod provider (`@riverpod`, `Provider(`)
  whose body `ref.watch`es something that isn't a repository, service,
  client, API, storage or config provider

**Why.** A new router restarts at `initialLocation`, or at the platform URL,
on every rebuild and every hot reload, and drops the stack. Watching auth
state in the router provider rebuilds the router on every sign-in.
**Fix.** A top-level `final`, a `late final` `State` field, or a keepAlive
provider that `ref.listen`s into a `refreshListenable`.
**Not flagged.** `build()` of a Riverpod `Notifier` (not a widget), and
`ref.watch(authRepositoryProvider)` (the instance never changes; the Code
With Andrea starter does this).

## NAV-009 multiple-routers

**Low**, reported once · detect: more than one `GoRouter` construction in
`lib/`.
**Why.** Two routers mean two URL sources of truth. Nested navigation
belongs in `ShellRoute`/`StatefulShellRoute`.
**Not flagged.** Nothing. If the constructions are separate apps (an
examples folder, distinct flavors with distinct trees), suppress it with a
reason.

## NAV-010 missing-auth-guard

**Medium**, reported once · go_router, not getx · detect: a route whose
last static segment is `login`, `sign-in`, `signin`, `sign_in`, `auth` …,
and no `redirect`/`onEnter` anywhere in the app.
**Why.** Without a router guard, each screen has to check auth itself, and a
deep link to any screen that forgot skips sign-in.
**Fix.** The note gives the profile's wiring (MVN notifier → `ValueNotifier`
refresh, MVVM repository as `refreshListenable`, Bloc stream adapter, …).
**Not flagged.** An app that swaps whole router configs or `MaterialApp`s on
auth state. Read it and suppress if that's the design.

## NAV-011 debug-log-diagnostics-in-release

**Low** · detect: `debugLogDiagnostics: true`.
**Why.** go_router logs every location, query string included, through
package:logging. Any root `Logger` listener (file logs, crash-reporter
breadcrumbs) receives them in release.
**Fix.** `debugLogDiagnostics: kDebugMode`.

## NAV-012 redirect-without-refresh

**Medium** · go_router · detect: a top-level `redirect` whose body reads
auth-like state (`auth…`, `isLoggedIn`, `signedIn`, `currentUser`,
`session…`, `isGuest` …), on a `GoRouter`/`RoutingConfig` with no
`refreshListenable`, while nothing in `lib/` calls `router.refresh()`.
**Why.** The redirect only runs on navigation. After sign-out, the user
stays on the protected screen until they tap something.
**Fix.** Pass the auth source (or a bridge `ValueNotifier`) as
`refreshListenable`.
**Not flagged.** Redirects that read an `InheritedWidget` through
`X.of(context)` or `context.watch` (go_router re-runs them on change), and
router providers that `ref.watch` state (NAV-008 reports that design
instead).

## Calibration

Calibrated on flutter/samples `compass_app`, `navigation_and_routing` and
four smaller samples, Wonderous, FluffyChat, Hiddify, the Code With Andrea
Riverpod starter, and the go_router and go_router_builder examples. False
positives found during calibration and fixed:
- NAV-001: a loading `RoutingConfig` duplicating the real one (now
  compared per router call)
- NAV-005: a `queryParameters:` argument of `Uri(...)` read as untrusted
  input (now only reads count)
- NAV-008: a Riverpod `Notifier.build()` treated as widget `build()`, and
  `ref.watch(authRepositoryProvider)`
- NAV-012: `userId` matching the auth vocabulary
- NAV-002: name matching across unrelated example apps
