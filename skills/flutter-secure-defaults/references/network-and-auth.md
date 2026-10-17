# Network and auth defaults

How to build the HTTP client, the login and refresh flow, and the
validation at the network boundary so they're safe by default. For *where*
each piece lives in your pattern, read `secure-defaults-by-layer.md`. For
pinning, user-installed CAs, ATS exceptions and cleartext manifests, use the
`flutter-security-audit` skill (`../flutter-security-audit/SKILL.md`, L4).

## Contents

1. One configured client
2. HTTPS only, and never accept every certificate
3. Login: what the client sends and keeps
4. Refresh and logout
5. Validate at the boundary (input and output)
6. Logging HTTP traffic
7. Timeouts, retries and redirects
8. Review questions

## 1. One configured client

Create **one** Dio (or `http.Client`) per backend, in the composition root or
a `core/network` provider, and inject it into sources. Every security setting
lives there: base URL, auth interceptor, logging, timeouts, and pinning if
the audit asks for it. A `Dio()` built inside a source or widget skips all of
it (and is ARCH-101 in a widget).

```dart
Dio buildApiClient({required AppConfig config, required TokenStorage tokens, required SessionEvents events}) {
  final options = BaseOptions(
    baseUrl: config.apiBaseUrl,                     // https://, chosen per flavor
    connectTimeout: const Duration(seconds: 10),
    receiveTimeout: const Duration(seconds: 20),
    responseType: ResponseType.json,
  );
  final dio = Dio(options);
  dio.interceptors.add(AuthInterceptor(tokens, refreshClient: Dio(options), onSignedOut: events.signedOut));
  if (kDebugMode) {
    dio.interceptors.add(LogInterceptor(requestHeader: false, requestBody: false, responseBody: false));
  }
  return dio;
}
```

## 2. HTTPS only, and never accept every certificate

- Write `https://` everywhere. A cleartext URL to your API (SEC-003) exposes
  every token and body to anyone on the Wi-Fi. Android's cleartext block and
  iOS ATS **don't protect Dart's sockets**: Flutter's `dart:io` uses its own
  BoringSSL stack, so `http://` from Dio just works, insecurely.
- Localhost, `10.0.2.2` (the Android emulator), LAN IPs and `.local` hosts are
  normal in development and in self-hosted or IoT apps, so the checker doesn't
  report them. Keep them in a debug flavor's config, not in production
  defaults.
- **Never** `badCertificateCallback = (_, __, ___) => true`, `onBadCertificate`
  returning `true`, or Dio's `validateCertificate: (…) => true` (SEC-006). It
  turns HTTPS into "encrypted to whoever answers". For a debugging proxy
  (Charles, mitmproxy), install its CA on the emulator or simulator. If you
  truly need a dev-only escape hatch, put it under `if (kDebugMode)` so
  release builds tree-shake it out. The checker grades that Low.

```dart
// Bad: every certificate accepted, in every build
(dio.httpClientAdapter as IOHttpClientAdapter).createHttpClient = () =>
    HttpClient()..badCertificateCallback = (cert, host, port) => true;

// Good: the platform's trust store (the default). Pinning, if needed, per the audit skill
final dio = Dio(BaseOptions(baseUrl: 'https://api.shop.dev'));
```

## 3. Login: what the client sends and keeps

- Send credentials only in the request **body** over HTTPS, never in the URL
  (`?password=`) and never in a GET. Servers, proxies and analytics log URLs
  (`SEC-token-in-url`, and NAV-006 for app routes).
- Use OAuth 2 / OIDC with **PKCE** for third-party or social login
  (`flutter_appauth`, or the platform SDKs). Don't embed a client secret: a
  mobile app is a public client (`SEC-secret-on-client`).
- Keep the **access token short-lived** (minutes) and the **refresh token
  rotating**. Store both through `TokenStorage`, never in state.
- Don't decode the JWT to make authorization decisions. Reading `exp` to
  refresh early is fine. Trusting `role` is not (audit AUTH-JWT,
  `SEC-client-side-authz`).
- A `local_auth` biometric prompt is a UX gate, not authentication (audit
  AUTH-BIOMETRIC). Use it to unlock a key the server trusts, or as a second
  step on top of the server session.
- Password fields: `obscureText: true`, the right `autofillHints`, and no
  logging. The `flutter-forms` skill owns this (`../flutter-forms/SKILL.md`,
  FORM-004).

## 4. Refresh and logout

The interceptor in `secure-defaults-by-layer.md` §1.2 is the reference
implementation. The rules it encodes:

| Rule | Why |
|---|---|
| Single-flight (`QueuedInterceptor`, or a shared `Completer`) | parallel 401s otherwise race to refresh; with rotating refresh tokens the losers revoke the winner and the user is logged out |
| The refresh call uses a client *without* the auth interceptor | a 401 on refresh otherwise recurses forever |
| Retry the original request once | a server that always says 401 must not loop |
| Refresh failure means sign-out, through a callback | the interceptor can't navigate; the session owner resets state and the router redirects |
| Never refresh on 403 | 403 is "you may not", not "your token expired" |

**Logout** clears credentials first, then user data, cookies and SDK
sessions, and resets session state (§1.4 of the by-layer file). Also call the
server's revoke endpoint (best effort), so a stolen refresh token stops
working.

## 5. Validate at the boundary (input and output)

Client validation is UX. The server validates again, always. But the client
must still treat what it **receives** as untrusted, because a compromised
server, a proxy or a malicious deep link can send anything.

**Responses.** Parse into typed DTOs at the source, and fail in one place
with a typed failure. Pattern matching makes the shape explicit:

```dart
final class UserDto {
  const UserDto({required this.id, required this.name});
  final String id;
  final String name;

  static UserDto fromJson(Object? json) => switch (json) {
        {'id': final String id, 'name': final String name} when id.isNotEmpty && name.length <= 200 =>
          UserDto(id: id, name: name),
        _ => throw const FormatException('unexpected user payload'),
      };
}
```

- Avoid `json['x'] as String` and `!` over untrusted JSON. A `TypeError` is a
  bug, not a handled failure (`flutter-error-handling`, ERR-003).
- Bound what you accept: page sizes, string lengths, file sizes before
  download (`Content-Length`), image dimensions.
- Never render server strings as HTML or pass them to `loadRequest` without an
  allow-list (`webview-and-links.md`).
- Map transport errors in the repository, and show user-safe messages
  (ERR-008). Server error bodies often echo internals.

**Input.** Validate type, length and format before sending (an email
regex, a numeric amount with bounds). Trim, and normalise Unicode where
identity matters (usernames). Never build SQL by interpolation (audit
COD-SQLI): use `?` placeholders or drift's typed queries. Treat deep-link
parameters, push payloads and `postMessage` data as untrusted input (the
`flutter-navigation` skill covers deep links, NAV-003 and NAV-005).

## 6. Logging HTTP traffic

- `LogInterceptor()` logs **request headers by default**, including
  `Authorization`, through `print`, which runs in release builds.
  `PrettyDioLogger()` logs **response bodies by default**: your login
  response with both tokens. Chucker and Alice keep full traffic in an in-app
  inspector. Add any of them only `if (kDebugMode)` (SEC-005), and even then
  prefer `requestHeader: false`.
- In sources and repositories, log `method path → status (duration)`, never
  bodies (SEC-011).
- A redacting interceptor is fine for release diagnostics:

```dart
final class RedactingLogInterceptor extends Interceptor {
  RedactingLogInterceptor(this._log);
  final void Function(String) _log;
  static const _sensitive = {'authorization', 'cookie', 'set-cookie', 'x-api-key'};

  @override
  void onResponse(Response<dynamic> response, ResponseInterceptorHandler handler) {
    final r = response.requestOptions;
    final headers = {
      for (final MapEntry(:key, :value) in r.headers.entries)
        key: _sensitive.contains(key.toLowerCase()) ? '<redacted>' : value,
    };
    _log('${r.method} ${r.uri.path} → ${response.statusCode} headers=$headers');
    handler.next(response);
  }
}
```

Note `r.uri.path`, not `r.uri`. The query string may carry tokens.

## 7. Timeouts, retries and redirects

- Always set connect and receive timeouts. A hung request holds a spinner and
  a socket forever.
- Retry only idempotent requests, only on transient failures, with backoff
  (`flutter-error-handling`, ERR-retry-non-idempotent).
- Dio follows redirects by default. If an endpoint may redirect to another
  host, check `response.realUri.host`. The `Authorization` header must not
  follow a redirect to a third party.
- WebSocket URLs are `wss://`, never `ws://` to a real host. Authenticate the
  socket with a short-lived ticket, not the long-lived refresh token.

## 8. Review questions

- Is there exactly one client per backend, with timeouts, the auth
  interceptor and debug-only logging?
- Does any code path accept all certificates, or reach an `http://` host?
- Do tokens appear in any URL, log, state object or error message?
- Is refresh single-flight and loop-free, and does a failed refresh sign the
  user out?
- Are responses parsed into validated DTOs, with bounded sizes?
- For a deep audit (pinning, ATS, network security config), was
  `flutter-security-audit` run? If not, say so.
