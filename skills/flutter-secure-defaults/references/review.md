# flutter-secure-defaults: review checklist and finding examples

Moved out of `SKILL.md` so writing code doesn't load it: read this file
when you review code in this area, or when `dart-flutter-review` sends
you here. Paths are relative to the skill folder.

## REVIEW checklist

Script rules (`SEC-0xx`; full detail, grading and false positives in
`references/rules.md`):

| ID | Name | Default severity | What to look for |
|---|---|---|---|
| SEC-001 | token-in-plain-storage | High (Medium for an unknown `.put` store; Low if Hive encryption exists in the project) | `prefs.setString('access_token', …)`, `box.put('refresh_token', …)`, `GetStorage().write('token', …)`, a `jwt`/`password` column in drift or sqflite |
| SEC-002 | auth-header-outside-data-layer | Medium | `'Authorization'`, `HttpHeaders.authorizationHeader`, `'Bearer $x'`, `X-Api-Key` in a widget, notifier, bloc, view model, state, use case or entity |
| SEC-003 | cleartext-http-url | Medium (Low for a link, or a debug/dev context) | `'http://api.example.org'`. Not reported: localhost, `10.0.2.2`, LAN IPs, `*.local`, dotless hosts, XML namespaces, hostless `'http://'` |
| SEC-004 | secret-in-log | Medium (High for analytics or crash reports, Low when `kDebugMode`-guarded, `dart:developer` `log`, push tokens or bare `headers`) | `print('…$accessToken')`, `log.severe('… $token')`, `logEvent(parameters: {'token': t})`, `Crashlytics.log('… $refreshToken')` |
| SEC-005 | http-logger-in-release | Medium (Low with headers and bodies off, or a custom sink) | `LogInterceptor()` (logs request headers by default), `PrettyDioLogger()` (response bodies by default), Chucker/Alice inspectors, all without `if (kDebugMode)` |
| SEC-006 | accept-any-certificate | High (Low under a debug guard) | `badCertificateCallback = (…) => true` or `{ return true; }`, `onBadCertificate: (_) => true`, `validateCertificate: (…) => true` |
| SEC-007 | webview-js-without-navigation-guard | Medium (High with a JS channel) | `JavaScriptMode.unrestricted` / `InAppWebView(` with no `onNavigationRequest`/`shouldOverrideUrlLoading`, or one that always allows |
| SEC-008 | hardcoded-secret | High for vendor formats (Medium for generic credentials, a Google key or a test key; Info for a Firebase apiKey or an anon JWT) | `sk_live_…`, `ghp_…`, `AKIA…`, private keys, JWTs with a privileged role, `user:pass@` URLs, `clientSecret = '<high-entropy>'` |
| SEC-009 | secret-in-build-config | Low (Medium for a secret-named value, a literal `defaultValue`, or a bundled `.env`) | `String.fromEnvironment('API_SECRET')`, `dotenv.env['CLIENT_SECRET']`, `@EnviedField(varName: 'X_SECRET')`, `- .env` under `flutter: assets:` |
| SEC-010 | token-in-global-or-ui-state | Medium for a public mutable global or static (Low for a private cache, a provider or UI state; Medium in HydratedBloc state) | `String? authToken;` at top level, `static String? cachedToken`, `final String accessToken` in a state class |
| SEC-011 | body-logged-in-data-layer | Low (Medium in an auth, user or payment file) | `print(response.data)`, `log(jsonEncode(request))`, `logger.d(res.body)` in a source, service or repository |
| SEC-012 | release-build-unobfuscated | Low | `flutter build apk|appbundle|ipa|ios|macos` in CI or a build script with no `--obfuscate` (debug and profile builds skipped) |

Reading-level findings (`SEC-<slug>`; the script can't see these):

| ID | Severity | Look for |
|---|---|---|
| SEC-no-logout-wipe | High | sign-out that resets UI state but leaves tokens, caches, the database, cookies or SDK sessions behind |
| SEC-refresh-not-single-flight | Medium | several parallel 401s each start a refresh (token rotation logs the user out), or the refresh call goes through the intercepted client (infinite loop) |
| SEC-keychain-survives-uninstall | Medium | iOS: no first-run `deleteAll()`, so a reinstall (or a new owner) is still signed in |
| SEC-secret-on-client | High | the app calls a third-party API with a secret key (payments, email, LLM, maps-server) instead of going through your backend |
| SEC-token-in-url | High | `?access_token=` / `?api_key=` in API URLs (logged by proxies and servers). For routes and deep links, see NAV-006 |
| SEC-unvalidated-response | Medium | `as String` / `!` casts over untrusted JSON, no size limit, server data rendered as HTML or passed to `loadRequest` |
| SEC-client-side-authz | High | a role, premium or `isAdmin` flag decided on the client and trusted (the server must decide). The audit has RES-CLIENT-ENT |
| SEC-pii-in-telemetry | Medium | email or phone as the analytics/crash user ID, `sendDefaultPii: true`, form values in breadcrumbs |
| SEC-sensitive-file-exposure | Medium | private data written to external or shared storage, a cache dir shared by `share_plus`, temp exports never deleted |
| SEC-webview-loadrequest-unvalidated | Medium | `loadRequest(Uri.parse(x))` where `x` comes from a deep link, push or server, with no allow-list at the call site |
| SEC-permission-overreach | Low | a permission requested at startup "just in case", or a broad one where a narrow one works |

**Owned elsewhere: cross-reference, don't re-report:**
- Logging form-field values (`controller.text`, `onChanged`/`onSaved` values,
  form-state values) is FORM-004 `field-value-logged`. See the `flutter-forms`
  skill (`../flutter-forms/SKILL.md`). SEC-004 deliberately skips those.
- Opening an untrusted URL is NAV-005 `untrusted-url-launch`, and secrets or
  PII in routes are NAV-006 `sensitive-data-in-route`. See the
  `flutter-navigation` skill (`../flutter-navigation/SKILL.md`).
- Raw error text shown to users is ERR-008 (`flutter-error-handling`).
- Mutable globals in general are ARCH-105, and hard-coded config is
  `AP-hardcoded-config-in-sources` (`flutter-architecture`).
- Pinning, user CAs, ATS and cleartext manifests, `allowBackup`, Keychain
  accessibility, FLAG_SECURE, clipboard, exported components, URL schemes,
  WebView file access, weak `Random()`, SQL injection, `local_auth`-only gates,
  JWT trust, permissions in manifests, RASP and attestation belong to
  `flutter-security-audit` (`scan.sh` IDs like `NET-NO-PINNING`,
  `STO-ALLOWBACKUP`, `WEB-FILE-ACCESS`).

**When not to flag:**
- A Firebase `apiKey` in `firebase_options.dart`, a Supabase anon key, a Stripe
  publishable key. These are public by design: check that they're restricted
  (App Check, row-level security), not that they're hidden.
- The data layer setting `Authorization`. That's exactly where it belongs.
- `http://` to localhost, the emulator host, LAN devices or `.local` names.
  Self-hosted and IoT apps have to reach LAN devices that lack TLS.
- A short-lived password in a login form's state while the user types. That's
  sanctioned by bloclibrary's login tutorial and by `formz`. Flag it only if
  it's persisted, logged (FORM-004) or kept after submit.

## Finding examples

Use the suite's finding format, so `dart-flutter-review` can merge findings:

```markdown
### [HIGH] Access token stored in SharedPreferences
- id: SEC-001
- where: lib/features/auth/data/sources/auth_local_source.dart:14
- evidence: `await _prefs.setString('access_token', token);`
- rule: tokens live in platform secure storage behind a data-layer source (flutter-secure-defaults › storage-and-privacy.md §1)
- why: SharedPreferences is a plain XML/plist file; it is in device backups and readable on a rooted or jailbroken phone
- fix: |
    final class TokenSource {
      const TokenSource(this._secure);
      final FlutterSecureStorage _secure;
      Future<void> save(String token) => _secure.write(key: 'access_token', value: token);
    }
- confidence: confirmed

### [MEDIUM] Notifier builds the Authorization header
- id: SEC-002
- where: lib/features/profile/presentation/notifier/profile_notifier.dart:20
- evidence: `Options(headers: {'Authorization': 'Bearer $accessToken'})`
- rule: MVN: the notifier calls a use case; the Dio provider's interceptor adds the header (secure-defaults-by-layer.md › MVN)
- why: the token now passes through presentation code, where it ends up in state, logs and tests; every call site must remember it
- fix: add `AuthInterceptor` to the Dio provider in core/network and delete the header here
- confidence: confirmed
```

Mask every secret in `evidence` (`sk_live_…(32 chars)`). Report a pattern-wide
problem **once**, with a few locations. Open the report with one line: the
profile, whether secure storage is a dependency, and whether the deep audit
ran (`mvn, flutter_secure_storage, deep audit: not installed`).
