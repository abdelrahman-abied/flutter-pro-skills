---
name: flutter-navigation
description: Write and review Flutter navigation that fits the app's own architecture and is secure by default. Covers go_router (redirect, onEnter, refreshListenable, ShellRoute, StatefulShellRoute, typed routes with go_router_builder), Navigator 2.0, named routes, deep links, web URLs, passing arguments, back button and PopScope. Places navigation per pattern. MVN uses ref.listen plus a router redirect fed by an auth notifier, MVVM views react to commands, Bloc uses BlocListener, and in GetX Get.toNamed is the idiom. Guards auth in the router, validates deep-link parameters, never trusts route extras, allow-lists url_launcher schemes, keeps tokens and PII out of URLs and clears the stack on logout. Includes a NAV checker. Use it whenever code navigates, adds a route, guard, tab shell or deep link, or someone asks how to navigate from a notifier, bloc or view model, even if they never say "routing".
license: MIT
metadata:
  author: abdelrahman-abied
  version: "1.4.1"
  suite: flutter-pro-skills
---

# Flutter navigation

Navigation is where architecture and security meet. The route table is the
app's public surface: every path is something a link, a notification or a
browser address bar can open, with any parameters it likes. And "where does
`context.go` go?" is a question every pattern answers differently.

This skill makes navigation code **clean** (decisions placed where the
project's pattern puts them) and **secure by default** (the router guards
access, and nothing from a URL is trusted). It adds per-architecture
placement, a review checklist and a checker. For step-by-step router and
platform setup (adding go_router, `usePathUrlStrategy`, Android intent
filters, iOS associated domains), defer to the official
`flutter-setup-declarative-routing` recipe from `flutter/agent-plugins` if
it's installed.

## Workflow

### 1. Detect the profile and the router

Look for a declared convention in your agent's project instructions file
(`AGENTS.md`, `CLAUDE.md`, `GEMINI.md`, `.cursor/rules/…`,
`.github/copilot-instructions.md`), such as "routes live in `Routes`", "we
use typed routes" or "auth is guarded in the router". A declared convention
wins. Then run the checker. It is read-only, needs only the Python standard
library, and doesn't need `pub get`:

```bash
python3 -I <skill-dir>/scripts/check_navigation.py <project-root>                 # text report
python3 -I <skill-dir>/scripts/check_navigation.py <project-root> --json          # schema flutter-pro-skills/flutter-navigation@1
python3 -I <skill-dir>/scripts/check_navigation.py <project-root> --files changed.txt  # diff review
python3 -I <skill-dir>/scripts/check_navigation.py <project-root> --profile bloc   # declared pattern wins
```

The CLI is `check_navigation.py <project-root> [--json] [--files <list>]
[--profile auto|mvn|mvvm|bloc|mvc|getx|provider|riverpod|setstate] [--max n]`.
`--files` takes a file of relative paths or a comma-separated list. The
whole project is still analysed, because route tables and route constants
span files. Exit `0` means a report was produced, and `2` is a usage error.
The profile and per-file roles come from the `flutter-architecture` checker
(`../flutter-architecture/scripts/arch_check.py --json`). If that sibling
is missing, the checker falls back to path-based detection and says so.

```text
== NAVIGATION
  profile: mvvm (arch_check, confidence high)
  classification: arch_check files[]
  router: go_router; 1 GoRouter instance(s), 7 routes (0 unresolved), 0 typed routes, 1 guards, 15 navigation calls
  [NAV-003] unvalidated-route-param (medium) x1 — A deep-link/route parameter is parsed or forced without validation ...
      lib/routing/router.dart:102  int.parse(state.pathParameters['id']!)   [a malformed link throws inside the route builder; ...]
```

Read the `router:` line before writing anything. It tells you whether the
app uses go_router, auto_route, GetX or plain `Navigator`, and whether it
has route constants or typed routes to follow. Check `pubspec.lock` for the
go_router version: `onEnter` needs 16.3, path regex constraints and route
`metadata` need 17.5, and URLs are case-sensitive from 15.0
(`references/go-router-patterns.md` has the table).

### 2. Place navigation where the pattern puts it

Logic classes decide *that* something happened. The view or the router
decides *where to go*. ARCH-102 and `AP-navigation-in-logic` (in
`flutter-architecture`) already flag `BuildContext`, `Navigator` and
`context.go` inside logic classes. This table says what to write instead:

| Pattern | Guards (auth, onboarding) | One-time navigation (after save, after login) | Logout |
|---|---|---|---|
| MVN | `redirect` reads the auth notifier with `ref.read`. The router lives in a keepAlive provider that `ref.listen`s the notifier into a `ValueNotifier` used as `refreshListenable` | `ref.listen` in the view's `build()`; react to a sealed state (`CheckoutPaid`) and `context.go` | the notifier sets signed-out, the redirect moves to the login route |
| MVVM (Flutter guide) | `redirect` + `refreshListenable: authRepository` (a `ChangeNotifier`), as in the Compass app | the view listens to a `Command` (`completed` / `error`), calls `clearResult()`, then `context.go` | `LogoutViewModel` calls the repository; the redirect does the rest |
| Bloc / Cubit | `redirect` reads the auth bloc's state; `refreshListenable` wraps `bloc.stream` in a `ChangeNotifier` | `BlocListener` (or `BlocConsumer.listener`), with `listenWhen` | emit unauthenticated; redirect, or `pushAndRemoveUntil` with plain Navigator |
| Riverpod (plain) | same as MVN, with `ref.read` inside `redirect` | `ref.listen` in a `ConsumerWidget` | invalidate the session providers, then let the redirect move |
| Provider | `refreshListenable: auth` (a `ChangeNotifier` above `MaterialApp.router`) | the view acts after awaiting the model call, or a listener on the model | the model notifies, and the redirect moves |
| GetX | `GetMiddleware.redirect` on `GetPage`s | `Get.toNamed` in the controller is the idiom, so it isn't flagged | `Get.offAllNamed(Routes.LOGIN)` |
| MVC / setState | `redirect` + `refreshListenable` on the auth model | the `State` navigates after the controller call returns (`if (!mounted) return;`) | redirect, or `pushNamedAndRemoveUntil(..., (_) => false)` |

Full code for each pattern (router wiring, the listener, logout, tests) is in
`references/placement-by-architecture.md`.

### 3. Write it secure by default

Follow the WRITE checklist below. Routing patterns (redirect, shells, typed
routes, error pages, back handling, deep-link tests) are in
`references/go-router-patterns.md`. The threat model and the validation
helpers are in `references/deep-links-and-security.md`.

### 4. Run the checker and confirm every hit

Read the code behind each hit before you call it `confirmed`.
`references/rules.md` lists each rule's false positives. Suppress a
deliberate hit in code, with a reason: `// nav-ignore: NAV-003 ids come
from our own QR codes` (on the line or the line above), or `//
nav-ignore-file: NAV-004 <reason>`.

## WRITE checklist (clean and secure by default)

1. **One router, created once.** Use a top-level `final`, a `State` field or a
   keepAlive provider. Never create it in `build()`, and never in a provider
   that `ref.watch`es changing state, because each rebuild resets the stack
   (NAV-008).
2. **Guard in the router, not in screens.** Put auth and onboarding rules in
   `redirect` (or `onEnter` on go_router ≥16.3). Feed it through
   `refreshListenable` so sign-in and sign-out re-run it (NAV-010, NAV-012).
   Return `null` once the user is at the target. A target rebuilt from the
   current URI (`/login?from=…`) differs on every pass and loops until
   `redirectLimit`.
3. **Keep redirects synchronous and cheap.** Read auth from memory (a
   repository field, notifier state). Never do storage, network or token
   refresh inside `redirect` (NAV-007).
4. **Route by constants or typed routes.** Use one `Routes` class, or
   go_router_builder `TypedGoRoute`s, or route names, and use them in every
   `go`/`push`. Follow what the project already does (NAV-002).
5. **Treat every path and query parameter as hostile input.** Use
   `int.tryParse`, `Enum.values.asNameMap()[raw]`, length limits and a
   not-found page. Or constrain the path (`':id(\\d+)'`, go_router ≥17.5),
   or use typed routes, which parse for you (NAV-003).
6. **Never put objects that matter in `extra`.** `extra` is gone on deep
   links, web refresh and restoration. Pass an id in the path and load the
   object. If you do pass `extra`, handle `null` (NAV-004). Never use
   `extra` or a query flag for authorisation; the server and the guard
   decide (NAV-extra-for-authorization).
7. **Keep tokens, passwords and PII out of locations.** URLs end up in
   browser history, router logs, analytics screen views and crash
   breadcrumbs. Pass secrets in memory. If an inbound link carries a
   one-time token (password reset, magic link), consume it in the guard,
   exchange it, then `go()` to a clean location (NAV-006).
8. **Allow-list before `launchUrl`.** Parse with `Uri.tryParse`, then accept
   only expected schemes (`https`, `mailto`, `tel`) and, for `https`,
   expected hosts. Never launch `javascript:`, `file:`, `intent:` or unknown
   custom schemes from a link, a notification or user text (NAV-005).
9. **Validate redirect targets.** A `?from=` value is accepted only if it is
   an in-app path: it starts with `/`, doesn't start with `//`, and matches
   a known route.
10. **Back handling.** On screens a deep link can open, use
    `context.canPop() ? context.pop() : context.go(Routes.home)`. Use
    `PopScope(canPop: …, onPopInvokedWithResult: …)`, not `WillPopScope`
    (deprecated, and it breaks Android predictive back).
11. **Logout clears the stack and the state.** Let the redirect `go` to the
    login route; never `push` it. Invalidate session providers, reset blocs
    and clear caches, so Back can't return to protected screens and no
    stale data survives.
12. **Gate diagnostics.** Use `debugLogDiagnostics: kDebugMode`, never `true`
    (NAV-011).
13. **Handle unknown locations.** Give the router an `errorBuilder` (or
    `onException`) that shows a not-found page with a way home. Don't let
    it fall through to a crash.

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

## Related skills

These assume the suite is installed as sibling folders. If your agent doesn't
auto-load skills, read the path given. If a sibling is missing, carry on and
say which check you skipped.

- **`flutter-architecture`** for detecting the pattern and the layer rules.
  ARCH-102, ARCH-111 and `AP-navigation-in-logic` live there. Fallback:
  `../flutter-architecture/SKILL.md`,
  `../flutter-architecture/references/anti-patterns.md`.
- **`flutter-secure-defaults`** for where tokens live, HTTPS, logging and
  WebView defaults. This skill covers only the navigation surface (guards,
  deep-link input, URLs). Fallback: `../flutter-secure-defaults/SKILL.md`.
- **`flutter-security-audit`** (a separate skill by the same author) for a
  deep audit: deep-link hijacking, exported components, MASVS mapping.
- **`flutter-ui-practices`** for `context.mounted` after `await`, listeners
  and lifecycle. Fallback: `../flutter-ui-practices/SKILL.md`.
- **`flutter-error-handling`** for turning a failed load after a deep link
  into error state, not a crash. Fallback: `../flutter-error-handling/SKILL.md`.
- **`flutter-testing`** for testing redirects and deep links (fake auth,
  `router.go` in widget tests). Fallback: `../flutter-testing/SKILL.md`.
- **`dart-flutter-review`** for full reviews; it merges NAV findings with
  the other passes. Fallback: `../dart-flutter-review/SKILL.md`.
- **`flutter-setup-declarative-routing`** (official, `flutter/agent-plugins`,
  if installed) for adding go_router, the URL strategy and platform
  deep-link setup.

## References

| File | Read it when |
|---|---|
| `references/placement-by-architecture.md` | wiring the router, guards, one-time navigation and logout for MVN, MVVM, Bloc/Cubit, Riverpod, Provider, GetX, MVC/setState, or answering "how do I navigate from my notifier/bloc/view model" |
| `references/go-router-patterns.md` | version-sensitive APIs, route constants vs typed routes, redirect/onEnter, ShellRoute vs StatefulShellRoute, passing arguments, error pages, back handling, web URLs, deep-link tests |
| `references/deep-links-and-security.md` | validating parameters, guards, open redirects, url_launcher allow-lists, tokens in URLs, verified app links, confirming link actions |
| `references/rules.md` | every NAV-0xx rule: detection, why, fix, false positives |
