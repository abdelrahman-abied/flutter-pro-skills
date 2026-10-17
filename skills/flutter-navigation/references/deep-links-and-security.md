# Deep links and navigation security

## Contents

- [1. Threat model](#1-threat-model)
- [2. Validate and sanitise every parameter](#2-validate-and-sanitise-every-parameter)
- [3. Guard in the router; authorise on the server](#3-guard-in-the-router-authorise-on-the-server)
- [4. Never trust extra or query flags](#4-never-trust-extra-or-query-flags)
- [5. Redirect targets and notification routes](#5-redirect-targets-and-notification-routes)
- [6. Allow-list before url_launcher](#6-allow-list-before-url_launcher)
- [7. Keep tokens and PII out of URLs](#7-keep-tokens-and-pii-out-of-urls)
- [8. Verified links over custom schemes](#8-verified-links-over-custom-schemes)
- [9. Confirm actions that links trigger](#9-confirm-actions-that-links-trigger)
- [10. Logout: clear the stack and the state](#10-logout-clear-the-stack-and-the-state)

This file covers the **navigation surface**. Where tokens are stored, HTTPS,
logging, WebView settings and release hardening belong to the
`flutter-secure-defaults` skill (`../flutter-secure-defaults/SKILL.md`). For
a full audit (deep-link hijacking, exported Android components, MASVS
mapping), load `flutter-security-audit` if it's installed.

## 1. Threat model

Every route is an entry point. A location can come from:

- a link in an email, SMS, chat message, QR code or web page
- another app firing an intent or opening your custom scheme
- a push-notification payload
- the browser's address bar, history and Back button (Flutter web)
- state restoration after the OS kills the process

Whoever sends the link controls the **path, query and fragment**. They don't
control `extra`, so on these entry points `extra` is simply **missing**. The
router is the one place every entry point passes through, which is why
guards and validation belong there.

## 2. Validate and sanitise every parameter

Parse parameters into typed values at the route boundary, and give each
failure a destination (a not-found page, or a redirect home), not an
exception:

```dart
extension RouteParams on GoRouterState {
  int? intParam(String name) => int.tryParse(pathParameters[name] ?? '');

  T? enumParam<T extends Enum>(String name, List<T> values) =>
      values.asNameMap()[pathParameters[name]];

  String? query(String name, {int maxLength = 200, RegExp? pattern}) {
    final raw = uri.queryParameters[name];
    if (raw == null || raw.isEmpty || raw.length > maxLength) return null;
    if (pattern != null && !pattern.hasMatch(raw)) return null;
    return raw;
  }
}

GoRoute(
  path: r'/orders/:id(\d+)',                       // go_router >= 17.5 rejects non-digits at match time
  builder: (context, state) => switch (state.intParam('id')) {
    final id? => OrderView(id: id, tab: state.query('tab', pattern: RegExp(r'^(items|tracking)$'))),
    null => const NotFoundView(),
  },
),
```

- Prefer `tryParse` and `asNameMap()[raw]` to `int.parse` and
  `values.byName` (NAV-003).
- Treat query parameters as optional by nature: `queryParameters['q'] ?? ''`,
  never `!` or `as String`.
- Check `pathSegments.length` before indexing. Custom-scheme links like
  `myapp:u` have fewer segments than you expect.
- Bound lengths, and match ids and slugs against a pattern before they reach
  a repository or a cache key.
- An id that parses is still not *authorised*. `/orders/42` must load
  through an API that checks the order belongs to the caller (insecure
  direct object reference, IDOR). The app can't enforce that.

## 3. Guard in the router; authorise on the server

- Put sign-in, onboarding and role rules in the top-level `redirect` (or
  `onEnter`), with `refreshListenable` following the auth source. A
  per-screen `if (!loggedIn) context.go('/login')` misses every screen
  that forgot it (NAV-per-screen-auth-check, NAV-010).
- Roles come from the server: decoded claims of a verified token, or a
  `/me` response kept in the auth repository. Never from local flags,
  `extra` or the URL.
- The client guard is UX. The server still rejects every unauthorised call.
  A guard that hides `/admin` doesn't protect the admin API.

## 4. Never trust extra or query flags

```dart
// Bad: anyone can open /settings?admin=true; extra is absent on deep links
GoRoute(path: '/settings', builder: (context, state) => SettingsView(
  isAdmin: state.uri.queryParameters['admin'] == 'true' || (state.extra as Map?)?['admin'] == true,
)),

// Good: the view asks the auth source; the server enforces it
GoRoute(path: '/settings', builder: (context, state) => const SettingsView()),
// SettingsView: final isAdmin = ref.watch(authNotifierProvider.select((s) => s.isAdmin));
```

`extra` is fine as an in-memory optimisation (a preloaded object, to skip a
refetch), provided the screen also works when it's `null` (NAV-004).

## 5. Redirect targets and notification routes

A `?from=` or `?next=` parameter is an **in-app open redirect** waiting to
happen. Accept only relative, in-app paths:

```dart
String safeReturnTo(String? raw, {String fallback = Routes.home}) {
  if (raw == null || raw.length > 512 || !raw.startsWith('/') || raw.startsWith('//')) return fallback;
  final uri = Uri.tryParse(raw);
  if (uri == null || uri.hasScheme || uri.hasAuthority) return fallback;
  return uri.toString();
}

// after sign-in
context.go(safeReturnTo(GoRouterState.of(context).uri.queryParameters['from']));
```

Push notifications are another link source. Map a notification **type** to
a route you build yourself, never `context.go(message.data['route'])`:

```dart
String? routeForNotification(Map<String, Object?> data) => switch (data) {
  {'type': 'order', 'orderId': final String id} when RegExp(r'^\d{1,12}$').hasMatch(id) => Routes.order(id),
  {'type': 'chat', 'roomId': final String id} when id.length <= 64 => Routes.chat(id),
  _ => null,                                          // unknown or malformed: open the app's home
};
```

## 6. Allow-list before url_launcher

`launchUrl` hands the URI to the OS. A link from outside can name any
scheme: `intent:` (Android), `javascript:` (web), `file:`, `sms:`/`tel:`
with premium numbers, or another app's custom scheme. Parse it, then
allow-list it (NAV-005):

```dart
const _schemes = {'https', 'mailto'};
const _hosts = {'example.com', 'help.example.com'};

Future<bool> launchTrusted(String raw) async {
  final uri = Uri.tryParse(raw.trim());
  if (uri == null) return false;
  final scheme = uri.scheme.toLowerCase();
  if (!_schemes.contains(scheme)) return false;
  if (scheme == 'https' && !_hosts.contains(uri.host.toLowerCase())) return false;
  return launchUrl(uri, mode: LaunchMode.externalApplication);
}
```

- For user-generated links (chat, comments), where any `https` host is
  legitimate, still restrict the **scheme**. Show the real URL before
  opening it when the visible text differs (FluffyChat asks for consent
  then, but it launches every non-http scheme without a check; don't copy
  that part).
- Open untrusted pages externally, or in the in-app browser view
  (`LaunchMode.inAppBrowserView`). Never open them in a WebView that has
  JavaScript channels (`flutter-secure-defaults` covers WebView defaults).
- `canLaunchUrl` answers "is there a handler?", not "is this safe?".

## 7. Keep tokens and PII out of URLs

Locations are copied into many places you don't control:

- browser history and sync, and the address bar in screenshots and screen shares
- `debugLogDiagnostics` output, which goes through package:logging in release too (NAV-011)
- analytics `NavigatorObserver`s that log screen names and route settings
- crash-reporter navigation breadcrumbs
- links the user copies and shares

So never navigate to `/session/$accessToken`, `/profile?email=…` or
`/verify/:otp` (NAV-006). Pass secrets in memory: a repository, notifier
state, or a short-lived in-memory handle keyed by an opaque id.

**Inbound one-time tokens** (password reset, magic link, email
verification) have to arrive in the URL. Consume them at the edge and move
on to a clean location:

```dart
// go_router >= 16.3
onEnter: (context, current, next, router) {
  if (next.uri.path != Routes.resetPassword) return const Allow();
  final token = next.uri.queryParameters['token'];
  if (token == null || token.length > 512) return const Block.stop();
  return Block.then(() {
    passwordResetRepository.hold(token);              // in memory, single use, exchanged server-side
    router.go(Routes.resetPasswordForm);              // the token never becomes the current location
  });
},
```

On older go_router, read it in a route-level `redirect`, hand it to the
repository, and return the clean location.

## 8. Verified links over custom schemes

- Any Android app can register the same custom scheme (`myapp://`). On iOS,
  which app gets a scheme claimed twice is undefined. Don't carry OAuth
  callbacks, payment results or invite tokens on a custom scheme without
  PKCE and server-side checks. Prefer **App Links** (Android,
  `android:autoVerify="true"` + `/.well-known/assetlinks.json`) and
  **Universal Links** (iOS, associated domains + `apple-app-site-association`).
- Claim only what you route. Use https only (no `http` data scheme in the
  intent filter), and narrow AASA `components` / intent-filter path
  prefixes to the paths in your route table. `"paths": ["*"]` hands every
  URL on the domain to the app (NAV-unverified-app-links).
- Platform setup steps live in the official
  `flutter-setup-declarative-routing` recipe. Check verification with
  `adb shell pm get-app-links <package>`.

## 9. Confirm actions that links trigger

A link is a request someone else wrote. Opening it must never *perform* a
state-changing action (pay, transfer, delete, accept an invite, follow,
import a configuration or profile). Route it to a screen that shows what
will happen and asks the signed-in user to confirm
(NAV-deep-link-action-without-confirmation). Hiddify shows a sheet before
importing a profile from a link; that is the right shape.

## 10. Logout: clear the stack and the state

1. Clear credentials in the data layer (`flutter-secure-defaults`).
2. Change auth state. The router redirect `go`es to the login route. `go`
   replaces the stack, and leaving a `StatefulShellRoute` drops every branch
   stack. Never `push` the login screen; Back would return to protected
   pages (NAV-logout-keeps-stack).
3. Reset per-user state:
   - MVN/Riverpod: providers that hold user data `ref.watch` the session, or
     get `ref.invalidate`d.
   - Bloc: emit cleared states, or recreate the blocs under a `BlocProvider`
     keyed by user id.
   - MVVM: repositories clear their caches (Compass resets the itinerary
     config).
   - GetX: `Get.offAllNamed(Routes.LOGIN)`, and clear permanent services.
4. On the web, Back after sign-out lands on an old URL. The router guard
   sends it to login again, which is one more reason the guard can't live
   in screens.
