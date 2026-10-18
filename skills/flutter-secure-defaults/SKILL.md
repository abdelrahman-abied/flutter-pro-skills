---
name: flutter-secure-defaults
description: Write and review Flutter/Dart code that is secure by default, each control in the right layer of the app's architecture (MVN, MVVM, Bloc, Clean, Provider, GetX). Tokens live in flutter_secure_storage behind a data-layer source, never SharedPreferences or UI state. Auth headers and token refresh go in a Dio/HTTP interceptor, and logout wipes everything. HTTPS only. No secrets in source, --dart-define or a bundled .env. No tokens or PII in logs, analytics or crash reports. Validate at boundaries, lock down WebViews, minimal permissions. Use it whenever code touches tokens, credentials, API keys, login, auth, sessions, interceptors, storage, HTTP clients, logging, WebViews or permissions, or the user asks "is this secure", "store the token" or "add login", even if nobody says "security". For a full release-build audit (pinning, RASP, obfuscation) use flutter-security-audit.
license: MIT
metadata:
  author: abdelrahman-abied
  version: "1.7.0"
  suite: flutter-pro-skills
---

# Flutter secure defaults

Most security bugs in Flutter apps aren't exotic. A token goes into
SharedPreferences because that's the storage the app already has. A widget
adds `'Authorization': 'Bearer $token'` because the token was right there. A
`print(response.data)` that helped debug login ships to production. None of
these needs an attacker with a debugger: a backup, a logcat dump, a crash
report or a proxy is enough.

This skill makes the safe choice the default one **while the code is being
written**, and puts each control where the app's architecture says it
belongs. Tokens live in a data-layer source, headers live in the HTTP client,
and the UI only ever sees "signed in as Alice". Code that follows these
defaults needs no later hardening pass for these issues.

It complements the separate **`flutter-security-audit`** skill by the same
author. That skill audits a finished app: RASP, obfuscation, certificate
pinning, attestation, screen protection, manifests and plists, with MASVS and
CWE tags and an attack playbook. This skill covers the code you write every
day. Its checker does not repeat the audit's scanner. Where they overlap, the
finding says so (see `references/rules.md`, "Overlap with scan.sh").

## Workflow

### 1. Detect the architecture and the project's decisions

Look first for declared security decisions in your agent's project
instructions file (`AGENTS.md`, `CLAUDE.md`, `GEMINI.md`, `.cursor/rules/…`,
`.github/copilot-instructions.md`), the README or ADRs: "tokens are in the
Keychain via X", "we pin with Y", "logs go to Sentry with scrubbing". A
declared decision wins. Then run the checker. It is read-only, needs only the
Python standard library, and doesn't need `pub get`:

```bash
python3 -I <skill-dir>/scripts/check_secure_defaults.py <project-root>                 # text report
python3 -I <skill-dir>/scripts/check_secure_defaults.py <project-root> --json          # schema flutter-pro-skills/flutter-secure-defaults@1
python3 -I <skill-dir>/scripts/check_secure_defaults.py <project-root> --files changed.txt   # diff review
python3 -I <skill-dir>/scripts/check_secure_defaults.py <project-root> --profile bloc   # declared pattern wins
```

The CLI is `check_secure_defaults.py <project-root> [--json] [--files <list>]
[--profile auto|mvn|mvvm|bloc|mvc|getx|provider|riverpod|setstate] [--max n]`.
`--files` takes a file of relative paths or a comma-separated list, and may
name `pubspec.yaml` or CI files. The exit code is `0` whenever a report is
produced and `2` on a usage error.

Layers and roles come from the `flutter-architecture` checker
(`../flutter-architecture/scripts/arch_check.py --json`, its `files[]`). If
that sibling is missing, the checker classifies by path and prints
`classification: path-based fallback (...)`. Besides Dart under `lib/`, it
reads `pubspec.yaml` (bundled `.env` assets) and CI and build scripts
(`.github/workflows/*`, `codemagic.yaml`, `fastlane/Fastfile`, `Makefile`,
`*.sh`).

```text
== SECURITY DEFAULTS
  profile: mvn (arch_check, confidence high)
  classification: arch_check files[]
  scanned: 142 Dart files, 3 config files (.github/workflows/release.yml, pubspec.yaml, scripts/build.sh)
  secure storage: flutter_secure_storage; http: dio
  deep audit: flutter-security-audit not installed (pinning, RASP, manifests, attestation not checked); install from https://github.com/abdelrahman-abied/flutter-security-audit
  [SEC-001] token-in-plain-storage (high) x1 — A token, password or secret is written to SharedPreferences, ...
      lib/features/auth/data/sources/auth_local_source.dart:14  await _prefs.setString('access_token', token);   [SharedPreferences (key 'access_token'); ...]
  [SEC-008] hardcoded-secret (info) x1 — ...
      lib/firebase_options.dart:50  apiKey: 'AIza…(39 chars)',   [Firebase apiKey: a public identifier by design, ...]
```

**Secret values are never printed.** A detected secret shows as its prefix and
length, like `AIza…(39 chars)`. Do the same in everything you write: never
paste a secret into a report, a chat message, a commit or an issue. Cite it as
"a hard-coded credential at `file:line`".

### 2. Put each default in its layer

The rule behind every row: **the token is a data-layer detail.** It is read
from secure storage by a source, attached by the HTTP client and refreshed by
an interceptor. Logic and UI see the session (`SignedIn(user)`), never the
credential.

| Concern | MVN | MVVM (Flutter guide) | Bloc / Cubit | Clean Architecture | Provider | GetX |
|---|---|---|---|---|---|---|
| Token storage | `data/sources/token_source.dart` (FlutterSecureStorage) + its `@riverpod` provider | `data/services/token_storage_service.dart` | a token-storage data provider used by `AuthenticationRepository` | `data/datasources/auth_local_data_source.dart` | `services/token_storage.dart` | `AuthService extends GetxService` backed by secure storage |
| Auth header + refresh | Dio provider in `core/network/` with an `AuthInterceptor` | `ApiClient` with an auth-header callback the `AuthRepository` sets | the API client's interceptor | `core/network/` interceptor, injected into remote data sources | the shared `http`/Dio client | `GetConnect.httpClient.addRequestModifier` / `addAuthenticator`, or a Dio interceptor |
| Session state | sealed `AuthState` in `presentation/state/` (user, no token) | `AuthRepository.isAuthenticated` + a `ChangeNotifier` | `AuthenticationBloc` with `AuthenticationStatus` + `User` | domain `Session`/`User` entity, no raw token | `AuthModel extends ChangeNotifier` (isSignedIn, user) | `Rx<User?>` in an `AuthController` |
| Logout wipe | `signOut` use case → repository clears source; `ref.invalidate` user providers | `logout` Command → repository clears storage and caches | `AuthenticationLogoutRequested` → repository clears, blocs reset | `SignOut` use case → repository → data sources | `AuthService.signOut()` then `notifyListeners()` | `AuthService.signOut()` then `Get.offAllNamed('/login')` |
| Log redaction | a `redact()` helper in `core/logging/` | `utils/` | `core/` | `core/` | `utils/` | `core/` |

Read `references/secure-defaults-by-layer.md` for the code of each pattern:
the token source, the interceptor with single-flight refresh, the session
state and the logout wipe.

### 3. Write with the checklist

Apply the **WRITE checklist** below. For the details, read the reference for
the topic you're touching: `references/network-and-auth.md` (HTTP clients,
login, refresh, TLS, validation), `references/storage-and-privacy.md`
(storage, logs, analytics, crash reports, files),
`references/secrets-and-config.md` (keys, flavors, `--dart-define`, `.env`)
and `references/webview-and-links.md` (WebViews, url_launcher, permissions).

### 4. Run the checker and confirm every hit

Read the code behind each hit before you call it `confirmed`.
`references/rules.md` lists each rule's grading and false positives. The
`note` column says why a hit got its severity: a `kDebugMode` guard lowers
it, an analytics call raises it, a Firebase `apiKey` is `info`. Suppress a
deliberate hit in code with a reason:
`// sec-ignore: SEC-003 the kiosk gateway has no TLS (SHOP-42)` on the reported
line or the line above, or `// sec-ignore-file: SEC-010 <reason>` anywhere in
the file. Use `# sec-ignore: …` in YAML and shell files.

### 5. Deep audits go to `flutter-security-audit`

For a security review, a hardening pass, a threat model, a pre-release check,
or anything about pinning, RASP, root or jailbreak detection, obfuscation
depth, attestation, screenshots or manifests: load the `flutter-security-audit`
skill. If your agent doesn't auto-load skills, read
`../flutter-security-audit/SKILL.md`. Then run its scanner
(`bash <its-dir>/scan.sh <project-root>`) and follow its report format. The
checker's `deep audit:` line says whether it found the skill. It looks for a
sibling folder, or the `FLUTTER_SECURITY_AUDIT_DIR` environment variable.

If it isn't installed, say so plainly: "the deep audit (pinning, RASP,
manifests, attestation, dependency CVEs) was not run". Suggest installing it
from github.com/abdelrahman-abied/flutter-security-audit, for example with
`git clone https://github.com/abdelrahman-abied/flutter-security-audit <skills-dir>/flutter-security-audit`.
Don't improvise its checks from memory, and never report "no pinning issues"
from a scan that didn't run.

## WRITE checklist

1. **Tokens go in platform secure storage.** Use `flutter_secure_storage`
   (Keychain / Keystore), wrapped in one data-layer source. On iOS, prefer
   `KeychainAccessibility.first_unlock_this_device`, which keeps the item out
   of iCloud backups. SharedPreferences, GetStorage, unencrypted Hive,
   drift/sqflite and files are plain text in the app sandbox and in device
   backups (SEC-001).
2. **The UI never holds the token.** States, notifiers, blocs, view models,
   controllers and providers expose `isSignedIn` and a `User`, not
   `accessToken`. No `static String? token` and no global (SEC-010).
   HydratedBloc persists state to disk, so never put a credential in hydrated
   state.
3. **One HTTP client and one interceptor add the header.** Widgets, logic and
   use cases never build `Authorization` (SEC-002). Refresh happens in that
   interceptor: one refresh at a time (`QueuedInterceptor`), on a second client
   without the auth interceptor, a single retry, and sign-out when the refresh
   fails.
4. **Logout wipes everything.** Delete the tokens, clear user caches and
   databases, cancel in-flight requests, reset session state, clear WebView
   cookies, and sign out of the Firebase, Google or Apple SDKs. On iOS the
   Keychain survives uninstall, so clear it on the first launch after
   install.
5. **HTTPS only.** No `http://` outside localhost and emulator hosts (SEC-003).
   Never return `true` from `badCertificateCallback`, `onBadCertificate` or
   `validateCertificate` (SEC-006). For a dev proxy, trust its CA on the
   emulator instead. Pinning is the audit skill's topic.
6. **No secrets in the app.** Anything in the binary is public: literals,
   `--dart-define`, `envied` and bundled `.env` files alike (SEC-008, SEC-009).
   Secrets live on your backend, and the app calls your backend. Only
   restricted, public client identifiers may ship (Firebase `apiKey`,
   Supabase anon key, Stripe publishable key, a Maps key restricted to your
   app).
7. **Log events, not values.** Never pass tokens, passwords, `Authorization`
   or request/response bodies to `print`, `debugPrint`, a logger, analytics or
   a crash reporter (SEC-004, SEC-011). Use `redact()` when you must identify
   a value. Add HTTP logging interceptors only `if (kDebugMode)` (SEC-005).
   Don't call `avoid_print` an "optional" lint.
8. **No PII in analytics or crash reports.** Use an opaque user ID, not an
   email. Set Sentry's `sendDefaultPii: false` and scrub in `beforeSend`.
   Never put form values or tokens in breadcrumbs or custom keys.
9. **Validate at every boundary.** Parse responses defensively, with typed
   DTOs, `fromJson` that checks types, and bounded sizes. Validate user input
   before sending it. Treat deep-link, push-payload and WebView-message data
   as untrusted. The server re-validates everything; the client check is UX.
10. **Lock down WebViews.** Turn JavaScript off unless the page needs it. When
    it's on, add an `onNavigationRequest` allow-list (and
    `useShouldOverrideUrlLoading: true` on flutter_inappwebview), and check
    the URL before `loadRequest` (SEC-007). Give it no file access and no JS
    channels for untrusted content.
11. **Allow-list what you open.** Only open `https` and the schemes you mean
    (`mailto:`, `tel:`) with url_launcher. Never put tokens or PII in URLs.
    The navigation skill owns these checks (NAV-005, NAV-006).
12. **Ask for the minimum.** Request a permission at the moment it is needed,
    with a reason, and only the narrowest one (coarse location, the photo
    picker instead of storage). The audit checks the merged manifest and
    plists (PRV-PERMS, PRV-IOS-PERMS). `flutter-platform-integration` covers
    the request flow (`PLAT-011` startup requests, `PLAT-012` permanent
    denial) and `flutter-release` the iOS usage strings (`REL-009`).
13. **Ship release builds with `--obfuscate --split-debug-info=<dir>`**, and
    keep the symbols as a private CI artifact (SEC-012). It is friction, not
    secrecy. For depth, see `flutter-security-audit` L1.1 and L7.2.
14. **Show user-safe errors.** Never show `e.toString()`, server messages
    with internals, or tokens in error text (ERR-008 in
    `flutter-error-handling`).

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

## Related skills

These assume the suite is installed as sibling folders. If your agent doesn't
auto-load skills, read the path given. If a sibling is missing, carry on and
say which check you skipped.

- **`flutter-security-audit`** (separate repo, same author) for the deep audit:
  `../flutter-security-audit/SKILL.md` and its `scan.sh`. If it's not
  installed, suggest github.com/abdelrahman-abied/flutter-security-audit.
- **`flutter-architecture`** for detecting the pattern and its layers.
  Fallback: `../flutter-architecture/SKILL.md`.
- **`flutter-feature-scaffold`** generates features that follow
  `references/secure-scaffold-checklist.md`. Fallback:
  `../flutter-feature-scaffold/SKILL.md`.
- **`flutter-navigation`** for deep-link validation, auth guards, NAV-005 and
  NAV-006. Fallback: `../flutter-navigation/SKILL.md`.
- **`flutter-forms`** for `obscureText`, autofill hints and FORM-004.
  Fallback: `../flutter-forms/SKILL.md`.
- **`flutter-error-handling`** for user-safe errors (ERR-008) and global crash
  reporting. Fallback: `../flutter-error-handling/SKILL.md`.
- **`flutter-networking`** for the client itself: one configured Dio/http
  client, timeouts, retry policy (NET-004), pagination and cancellation. The
  auth interceptor and transport security stay here. Fallback:
  `../flutter-networking/SKILL.md`.
- **`flutter-platform-integration`** for channels, FFI and permission
  requests (no secrets over channels, libraries never loaded from writable
  paths, PLAT-007). Fallback: `../flutter-platform-integration/SKILL.md`.
- **`flutter-release`** for signing, flavors and CI secrets (REL-010/011/012).
  Fallback: `../flutter-release/SKILL.md`.
- **`dart-flutter-review`** runs this checker and a security reviewer pass.
  Fallback: `../dart-flutter-review/SKILL.md`.

## References

| File | Read it when |
|---|---|
| `references/secure-defaults-by-layer.md` | writing the token source, the interceptor, the session state and the logout for MVN, MVVM, Bloc, Clean, Provider, GetX or Riverpod |
| `references/network-and-auth.md` | building an HTTP client, login, refresh, TLS settings, timeouts, or response and input validation |
| `references/storage-and-privacy.md` | storing anything, logging, analytics, crash reporting, files and caches (clipboard and screenshots defer to the audit) |
| `references/secrets-and-config.md` | API keys, flavors, `--dart-define`, `.env`/envied, what's public by design, what to do after a leak |
| `references/webview-and-links.md` | WebViews, url_launcher, deep-link input and permissions |
| `references/secure-scaffold-checklist.md` | generating or reviewing feature templates: the rules every scaffolded file follows |
| `references/rules.md` | every SEC-0xx rule (detection, grading, false positives, bad/good code) and the overlap map with `scan.sh` |
