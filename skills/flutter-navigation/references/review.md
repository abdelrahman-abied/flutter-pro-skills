# flutter-navigation: review checklist and finding examples

Moved out of `SKILL.md` so writing code doesn't load it: read this file
when you review code in this area, or when `dart-flutter-review` sends
you here. Paths are relative to the skill folder.

## REVIEW checklist

Script rules (`NAV-0xx`; the full detail is in `references/rules.md`):

| ID | Name | Default severity | What it finds |
|---|---|---|---|
| NAV-001 | duplicate-route-path | Medium | two `GoRoute`s resolving to the same URL (resolved through route constants and nesting); the second is unreachable |
| NAV-002 | raw-path-string | Low | `context.go('/x')`, `Navigator.pushNamed(context, '/x')`, `Get.toNamed('/x')` when route constants, typed routes or a named route for that path exist |
| NAV-003 | unvalidated-route-param | Medium (Low for a redirect target) | `int.parse`/`DateTime.parse`/`values.byName` of a path or query parameter; `queryParameters['x']!`; `pathSegments[n]` with no length check; `go(from)` from the query string with no check |
| NAV-004 | extra-hard-cast | Medium | `state.extra as T` / `state.extra!` / `settings.arguments as T` with no null handling |
| NAV-005 | untrusted-url-launch | Medium | `launchUrl`/`launchUrlString` of a URL from a route parameter, `state.uri`, a notification payload, an `href` or a text field, with no scheme or host check |
| NAV-006 | sensitive-data-in-route | High for secrets, Medium for one-time tokens and PII | `:token`/`:email` path params, `$accessToken`/`${user.email}` in a location, sensitive `queryParameters` keys, sensitive typed-route fields |
| NAV-007 | io-in-redirect | Medium | `SharedPreferences.getInstance`, secure-storage reads, HTTP/Dio, Firestore, `getIdToken`, `await …fetch/refresh(…)` inside `redirect`/`onEnter` |
| NAV-008 | router-recreated | Medium | `GoRouter(` in a widget's `build()`, a router factory called from `build()`, or a router provider that `ref.watch`es state |
| NAV-009 | multiple-routers | Low (once) | more than one `GoRouter` constructed in `lib/` |
| NAV-010 | missing-auth-guard | Medium (once) | a sign-in route exists but no `redirect`/`onEnter` anywhere (go_router apps) |
| NAV-011 | debug-log-diagnostics-in-release | Low | `debugLogDiagnostics: true` not gated by `kDebugMode` |
| NAV-012 | redirect-without-refresh | Medium | a top-level redirect reads auth state, but there's no `refreshListenable` and no `router.refresh()` |

Reading-level findings (`NAV-<slug>`; the script can't see these):

| ID | Severity | Look for |
|---|---|---|
| NAV-per-screen-auth-check | Medium | screens check `isLoggedIn` in `build`/`initState` and navigate to login; a deep link to any other screen skips the check |
| NAV-extra-for-authorization | High | access decided from `extra`, a query flag (`?admin=1`) or a client-side role passed between screens |
| NAV-logout-keeps-stack | High | logout `push`es the login screen, or leaves session providers, blocs and caches alive; Back returns to protected data |
| NAV-pop-without-fallback | Medium | `context.pop()`/`Navigator.pop` on a deep-linkable screen with no `canPop()` fallback ("There is nothing to pop", or the app closes) |
| NAV-deep-link-action-without-confirmation | Medium | a link performs a state-changing action (pay, delete, import, follow, accept an invite) without user confirmation |
| NAV-unverified-app-links | Medium | auth callbacks or sensitive actions on a custom scheme (any app can claim it) instead of verified App Links/Universal Links; an AASA `"paths": ["*"]` broader than the route table |
| NAV-navigate-in-build | Medium | `go`/`push` called while building (assertions, loops); move it to a listener or the redirect |
| NAV-redirect-loop | Medium | redirects that disagree (onboarding sends to `/login`, auth sends back) or rebuild the target from the current URI (`/login?from=/login?from=…`); go_router stops at `redirectLimit` and shows the error page |
| NAV-imperative-push-in-router-app | Low | `Navigator.push(MaterialPageRoute(...))` for full screens in a go_router app; the screen has no URL, the guard doesn't run, and web Back is wrong. Dialogs and sheets are fine |
| NAV-wrong-shell | Low | `ShellRoute` where tabs must keep their stacks (use `StatefulShellRoute.indexedStack`), or tab taps not using `goBranch(i, initialLocation: i == currentIndex)` |
| NAV-willpopscope | Low | `WillPopScope` or `onPopInvoked` (deprecated); use `PopScope` + `onPopInvokedWithResult`. Report it once, alongside `LINT:deprecated_member_use` |
| NAV-no-error-page | Low | no `errorBuilder`/`errorPageBuilder`/`onException`; unknown links show the default error screen with the raw exception |

These are owned elsewhere, so cross-reference them instead of re-reporting
them:
- navigation inside logic classes is ARCH-102 / `AP-navigation-in-logic`
  (`flutter-architecture`)
- `context` after `await` is `UI-context-after-await` /
  `use_build_context_synchronously` (`flutter-ui-practices`)
- `shouldNavigate` bools in state are ARCH-111
- secrets in logs and storage are `flutter-secure-defaults`

**When not to flag:**
- `Get.toNamed` / `Get.offAllNamed` in a GetX controller. That is the
  pattern's idiom.
- Raw path strings in a project that consistently uses them and has no route
  constants (FluffyChat does this). NAV-002 only fires when an alternative
  exists.
- `state.pathParameters['id']!`. A matched route always has its path
  parameters. Only *parsing* them is the risk.
- An `async` redirect that awaits a cached getter (Compass awaits
  `isAuthenticated`, which returns a cached value after the first call).
- A dedicated, injected and tested navigation service that the project uses
  consistently. That's a deliberate choice (see `AP-navigation-in-logic`).
- `ref.watch` of a repository provider in the router provider (it never
  changes). Only watching *state* recreates the router.

## Finding examples

Use the suite's finding format, so `dart-flutter-review` can merge the
findings:

```markdown
### [MEDIUM] Booking id parsed without validation
- id: NAV-003
- where: lib/routing/router.dart:102
- evidence: `final id = int.parse(state.pathParameters['id']!);` in the `/booking/:id` builder
- rule: deep-link parameters are untrusted input (flutter-navigation › deep-links-and-security.md §2)
- why: `/booking/abc` from a shared link throws FormatException inside the builder; the user sees an error screen instead of "booking not found"
- fix: |
    GoRoute(
      path: r':id(\d+)',                       // go_router >= 17.5: non-digits never match
      builder: (context, state) {
        final id = int.tryParse(state.pathParameters['id'] ?? '');
        if (id == null) return const NotFoundScreen();
        return BookingScreen(viewModel: BookingViewModel(...)..loadBooking.execute(id));
      },
    ),
- confidence: confirmed

### [HIGH] Logout pushes the login screen over protected routes
- id: NAV-logout-keeps-stack
- where: lib/features/settings/presentation/view/settings_view.dart:58
- evidence: `await ref.read(signOutProvider)(); if (context.mounted) context.push(Routes.login);`
- rule: MVN: sign-out changes auth state, and the router redirect moves the user (placement-by-architecture.md §MVN)
- why: Back returns to the account screen with the previous user's data still in memory
- fix: drop the push; let `redirect` send signed-out users to `Routes.login` (the router's `refreshListenable` follows the auth notifier) and `ref.invalidate` the session providers in the sign-out use case
- confidence: confirmed
```

Open the report with one line naming the profile and the router
(`mvn, go_router 16.2, route constants, 1 guard`). Report a pattern-wide
problem **once**, with a few locations.
