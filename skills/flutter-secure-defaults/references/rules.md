# SEC rule catalog

Every rule that `scripts/check_secure_defaults.py` reports has an entry here,
with its default severity, how it's detected, how it's graded, why it
matters, bad and good Dart, and known false positives. The reading-level
`SEC-<slug>` findings are listed in SKILL.md's REVIEW checklist. Severities
use the suite scale: High means exposure under ordinary conditions (a backup,
a proxy, a log), Medium is a weak default or one that depends on context,
Low is hygiene, and Info is not a defect.

## Contents

- How the checker works
- Overlap with scan.sh (flutter-security-audit)
- What other suite skills own
- SEC-001 token-in-plain-storage
- SEC-002 auth-header-outside-data-layer
- SEC-003 cleartext-http-url
- SEC-004 secret-in-log
- SEC-005 http-logger-in-release
- SEC-006 accept-any-certificate
- SEC-007 webview-js-without-navigation-guard
- SEC-008 hardcoded-secret
- SEC-009 secret-in-build-config
- SEC-010 token-in-global-or-ui-state
- SEC-011 body-logged-in-data-layer
- SEC-012 release-build-unobfuscated
- Calibration notes

## How the checker works

- **Scope.** `lib/**.dart` (skipping generated files: `*.g.dart`,
  `*.freezed.dart`, `*.gr.dart`, `*.mocks.dart`, `*.config.dart`,
  `*.chopper.dart`, `*.pb*.dart`, `app_localizations*`, `messages_*`, and
  files headed "GENERATED CODE - DO NOT MODIFY"), plus `pubspec.yaml` and CI
  and build files (`.github/workflows/*.yml`, `codemagic.yaml`, `bitrise.yml`,
  `.gitlab-ci.yml`, `fastlane/Fastfile`, `Makefile`, `melos.yaml`, and `*.sh`
  in the root, `scripts/`, `tool/` or `ci/`). Tests aren't scanned.
- **Lexing.** Comments are stripped, so a comment *about* a token is never a
  finding. Structural rules run on a copy with string contents blanked.
  Rules that need string contents (URLs, keys, interpolations) read them
  separately.
- **Names, not words.** Logging and storage rules look for secret-named
  *expressions* (`accessToken`, `refresh_token`, `request.headers`,
  `['access_token']`), split by camelCase and snake_case. Names like
  `cancelToken`, `nextPageToken`, `fcmToken`, `designTokens`, `tokenExpiry`,
  `passwordVisible`, `hasToken`, `isTokenValid` and `tokenKey` don't count.
  Neither do properties like `token.isNotEmpty` and `token.length`, or
  comparisons like `${token != null}`. A sentence like
  `print('token refreshed')` never matches.
- **Layers and roles.** From `../flutter-architecture/scripts/arch_check.py
  --json` (`files[]`) when installed, otherwise from the path (the suite's
  §5 classification), and the output says which. Content refines the role: a
  class extending `Interceptor`, `QueuedInterceptor`, `GetConnect` or
  `GetxService` is data-layer code.
- **Grading.** The `note` explains every grade: debug guards (`kDebugMode`,
  `!kReleaseMode`, `assert`) lower it, and off-device sinks (analytics, crash
  reports) raise it.
- **Masking.** Every `evidence` string passes through a masker. Vendor-format
  secrets, values assigned to secret-named fields, and long high-entropy
  literals become `prefix…(N chars)`. The prefix is the vendor prefix
  (`sk_live_`, `AIza`, `eyJ`) or at most 4 characters.
- **Suppression.** `// sec-ignore: SEC-001 <reason>` on the reported line or
  the line above. `// sec-ignore-file: SEC-003 <reason>` anywhere in the
  file. `#` comments work in YAML and shell files. List several IDs with
  commas. Suppressed hits go to `suppressed` with their reason.
- **`--files`.** The whole project is analysed. Only findings in the listed
  files (Dart, `pubspec.yaml` or CI files) are reported.
- **Deep audit line.** The checker looks for `flutter-security-audit` as a
  sibling folder (`../flutter-security-audit/scan.sh` from the skills
  directory) or at `$FLUTTER_SECURITY_AUDIT_DIR`, and prints either the
  command to run or the install URL. It never runs `scan.sh` itself.

## Overlap with scan.sh (flutter-security-audit)

The audit's `scan.sh` is the deep, MASVS-tagged pass. This checker
implements only code-level write-time defaults. Where both look at the same
thing, this checker adds layer awareness, grading and masking, and the note
names the scan.sh check.

| scan.sh check | This checker | Difference |
|---|---|---|
| `STO-TOKEN-PREFS` | SEC-001 | adds Hive, GetStorage, generic `.put` stores, drift and sqflite columns, and key constants (`_tokenKey`, `Keys.accessToken`); skips `refresh` timestamps (`last_refresh_time`) |
| `NET-ACCEPT-ALL` | SEC-006 | adds block bodies (`{ return true; }`), `onBadCertificate`, Dio `validateCertificate`; grades debug-only guards Low |
| `PRV-LOG-LEAK` | SEC-004 | needs a secret-named *expression*, not a substring (scan.sh matches `pin` in "Skipping"/"Ping" and `token` in prose); adds `log.x(…)`, Talker and `logging` loggers, analytics and crash-report calls (High); leaves form-field values to FORM-004 |
| `SEC-HARDCODED`, `SEC-CLOUDKEY` | SEC-008 | masks values (scan.sh prints the line as-is); more vendor formats; grades a Firebase `apiKey` and an anon JWT as Info (public by design) instead of Critical; decodes JWT roles (`service_role` is High) |
| `WEB-JS-CHANNEL` | SEC-007 | reports JavaScript **without a navigation guard**, not every JS use; a JS channel raises it to High; flutter_inappwebview's default-on JS and dead `shouldOverrideUrlLoading` |
| `NET-CLEARTEXT` (manifest/plist) | SEC-003 | complementary: SEC-003 finds `http://` literals in Dart, which no platform setting blocks for Dart sockets |
| `COD-DEBUG-PRINT` | not repeated | every `print` is the `avoid_print` lint's job; SEC-004 reports only prints of secrets |
| hardening checklist L1.1 / L7.2 (manual) | SEC-012 | scan.sh doesn't automate this; SEC-012 reads CI and build scripts |

**Not implemented here, by design** (run `scan.sh`): `NET-USER-CA`,
`NET-INVALID-OK`, `NET-NO-PINNING`, `NET-ATS-EXCEPTION`, `STO-KEYCHAIN`,
`STO-IOS-KEYCHAIN`, `STO-ALLOWBACKUP`, `STO-NO-SECURE`, `STO-CLIPBOARD`,
`PLT-NO-FLAGSEC`, `PLT-ISCAPTURED`, `PLT-DEBUGGABLE`, `PLT-TASKALLOW`,
`PLT-TAPJACK`, `PLT-NO-APPLINKS`, `WEB-FILE-ACCESS`, `IPC-EXPORTED`,
`IPC-URLSCHEME`, `CRY-WEAK-RANDOM`, `AUTH-BIOMETRIC`, `AUTH-JWT`, `COD-SQLI`,
`PRV-PERMS`, `PRV-IOS-PERMS`, `RES-NO-ATTEST`, `RES-CLIENT-ENT`,
`RES-NO-RASP`, `COD-DEPRECATED`.

**ID note.** scan.sh's own IDs `SEC-HARDCODED` and `SEC-CLOUDKEY` share the
`SEC-` prefix. This skill's script IDs are always numeric (`SEC-0xx`), and
its reading-level IDs are lowercase slugs (`SEC-no-logout-wipe`). When you
merge both reports, keep scan.sh IDs verbatim and dedupe by `file:line`.

## What other suite skills own

| Topic | Owner | Why this checker skips it |
|---|---|---|
| Logging form-field values (`controller.text`, `onChanged`/`onSaved` values, formz `input.value`) | `flutter-forms` FORM-004 field-value-logged (see `../flutter-forms/SKILL.md`) | SEC-004 drops chains ending in a controller's `.text` or a form input's `.value`, form-callback parameters, and form-state segments |
| Opening untrusted URLs | `flutter-navigation` NAV-005 untrusted-url-launch | not re-implemented; `webview-and-links.md` shows the helper |
| Tokens and PII in routes and deep links | `flutter-navigation` NAV-006 sensitive-data-in-route | not re-implemented |
| Raw errors shown to users | `flutter-error-handling` ERR-008 | not re-implemented |
| Mutable globals in general | `flutter-architecture` ARCH-105 | SEC-010 reports only secret-named ones, and notes the overlap |

---

## SEC-001 token-in-plain-storage

**High** (Medium for an unknown key-value store, Low for Hive when the
project has an `encryptionCipher`) · detect: script

**Problem.** A token, password or secret goes into storage that is a plain
file: `SharedPreferences` (`setString`/`setStringList`), `GetStorage().write`,
a Hive `box.put` without encryption, any `.put(<secret-named key>, …)`, a
drift companion or sqflite `insert`/`update` with a `jwt`/`token`/`password`
column.
**Why.** These files are readable on rooted or jailbroken devices, are
included in device backups, and are copied by forensic tools. Secure storage
uses the Keychain and Keystore, which keep the key material out of the app's
files.

```dart
// Bad
await prefs.setString('access_token', token);
await GetStorage().write('refreshToken', refresh);
await db.insert('accounts', {'user': u, 'password': p});

// Good: one data-layer source over flutter_secure_storage
await tokenStorage.save(access: token, refresh: refresh);
```

**Grading.** SharedPreferences, GetStorage, plain Hive and plain databases are
High. An unknown store (`Store.put(StoreKey.accessToken, …)`) is Medium:
confirm whether it's encrypted. Hive is Low if any box in the project uses
`encryptionCipher`, because the checker can't tell which box it is. The
database check is skipped when `sqlcipher_flutter_libs`/`sqflite_sqlcipher`
is a dependency or a `PRAGMA key` exists. Database hits are reported once
per file.
**False positives.** A key named like a token that holds something else
(`'token_expiry'` and `'last_refresh'` are already skipped). A hashed PIN
column (still crackable offline for short PINs, so keep it Medium at least).

## SEC-002 auth-header-outside-data-layer

**Medium** · detect: script (presentation or domain layer, or the view,
widget, logic, state, event, use-case or entity role; paths under `data/`,
`network/`, `api/`, `services/`, `*_client.dart` and so on are exempt)

**Problem.** `'Authorization'`, `HttpHeaders.authorizationHeader`,
`'Bearer $x'`, `'X-Api-Key'` or `'X-Auth-Token'` appears in UI, logic or
domain code.
**Why.** The token then flows through presentation code, where it ends up in
state, logs, observers and tests. Every call site must remember to add it,
and one forgets.

```dart
// Bad (a notifier)
await dio.get('/me', options: Options(headers: {'Authorization': 'Bearer $token'}));

// Good: the shared client's interceptor adds it; the notifier calls a use case
final user = await ref.read(getProfileProvider)();
```

**Fix** per pattern: the note carries the profile's placement (see
`secure-defaults-by-layer.md`).
**False positives.** A composition-root file that wires the client, when it
is misclassified (move it under `core/network/` or suppress it with a reason).

## SEC-003 cleartext-http-url

**Medium** (Low for a link with no API call nearby, or in a debug, dev, mock
or demo context) · detect: script over string literals

**Problem.** A non-local `http://` URL in Dart code.
**Why.** Requests, tokens and bodies cross the network in clear text. Dart's
sockets aren't constrained by Android's cleartext setting or iOS ATS.

**Not reported:** `localhost`, `127.*`, `10.0.2.2`, `10.0.3.2`, `0.0.0.0`,
private LAN ranges, `*.local`/`*.test`/`*.internal`, `example.*`, dotless
hostnames, XML/RDF namespaces (`www.w3.org`, `schemas.android.com`, …),
hostless `'http://'` (scheme checks), localization files.

```dart
// Bad
final dio = Dio(BaseOptions(baseUrl: 'http://api.shop.app'));
// Good
final dio = Dio(BaseOptions(baseUrl: config.apiBaseUrl)); // https://, per flavor
```

**False positives.** Self-hosted apps whose default server really is plain
HTTP on a public host. Suppress it with the reason, and prefer making the
user type the URL.

## SEC-004 secret-in-log

**Medium** (High for analytics and crash-report calls; Low when debug-guarded,
for `dart:developer` `log()`, for push/FCM tokens, and for whole `headers` in
a file that sets no auth header) · detect: script

**Problem.** A secret-named expression (or an interpolated `Authorization:`,
`Bearer` or `Cookie` value) is an argument of `print`, `debugPrint`, `log`,
`developer.log`, a `logger.x`/`log.x`/`talker.x` call, or an analytics or
crash call (`logEvent`, `setUserProperty`, `setCustomKey`, `addBreadcrumb`,
`captureMessage`, `track`, `identify`, `Crashlytics.log`, `Breadcrumb(…)`).
**Why.** `print` and `debugPrint` run in release builds. Logs reach
crash-reporter breadcrumbs, support bundles and `adb logcat`. Analytics and
crash calls send the value to a third party by design.

```dart
// Bad
log.severe('Failed to update auth info with access token: $accessToken');
FirebaseCrashlytics.instance.log('signed in with $refreshToken');

// Good
log.severe('Failed to update auth info (token ${redact(accessToken)})');
```

**Skipped (owned by FORM-004 in `flutter-forms`):** `controller.text`,
form-callback parameters (`onChanged: (password) => …`), formz
`password.value`, and expressions through `form`, `formState` or `fields`.
**False positives.** A variable named `token` that holds a non-secret (rename
it). Push tokens are reported Low on purpose.

## SEC-005 http-logger-in-release

**Medium** (Low when headers and bodies are off, or the logger has a custom
`logPrint` sink) · detect: script (`LogInterceptor`, `PrettyDioLogger`,
`TalkerDioLogger`, `AwesomeDioInterceptor`, `CurlLoggerDioInterceptor`,
`ChuckerDioInterceptor`, `AliceDioAdapter`/`alice.getDioInterceptor()`,
`RequestsInspectorInterceptor`) outside a debug guard

**Why.** Dio's `LogInterceptor` defaults to `requestHeader: true`, so it logs
`Authorization` through `print`. `PrettyDioLogger` defaults to
`responseBody: true`, so it prints login responses with tokens. In-app
inspectors keep full traffic on the device and show it to whoever holds it.

```dart
// Bad
dio.interceptors.add(LogInterceptor());
// Good
if (kDebugMode) dio.interceptors.add(LogInterceptor(requestHeader: false));
```

**False positives.** A guard the checker doesn't recognise (a custom
`if (env.verbose)` flag). Recognised flags are `kDebugMode`, `!kReleaseMode`,
`kProfileMode`, `assert`, and names like `isDebug*`, `isDev*`, `devMode`,
`enableLog*`, `Flavor.dev`. Suppress with the reason.

## SEC-006 accept-any-certificate

**High** (Low under a debug guard) · detect: script
(`badCertificateCallback`, `onBadCertificate`, `validateCertificate`
assigned `(…) => true` or `{ return true; }`)

**Why.** Any certificate is accepted, so any proxy or attacker on the path
reads and changes all traffic, tokens included. This is the most common way
HTTPS gets switched off "temporarily" and shipped.

```dart
// Bad
client.badCertificateCallback = (cert, host, port) => true;
// Good: delete it; for a dev proxy, trust its CA on the emulator
```

**False positives.** None in release code. A callback that checks the host
or fingerprint isn't reported.

## SEC-007 webview-js-without-navigation-guard

**Medium** (High when the file also adds a JS channel or handler) · detect:
script, per file

**Problem.** `JavaScriptMode.unrestricted`, `javaScriptEnabled: true` or an
`InAppWebView(` (JS on by default) with no `onNavigationRequest` /
`shouldOverrideUrlLoading` in the file, or with one that always allows. Also
reported: `shouldOverrideUrlLoading` without
`useShouldOverrideUrlLoading: true`, which never fires.
**Why.** Every page the WebView reaches, including redirects and links,
runs script in your app, with your cookies and any JS bridge.

```dart
// Bad
WebViewController()..setJavaScriptMode(JavaScriptMode.unrestricted)..loadRequest(Uri.parse(url));
// Good: see webview-and-links.md §1 (allow-list in the delegate and before loadRequest)
```

**False positives.** A controller configured in one file and its delegate in
another (the check is per file). Suppress with the reason, or co-locate them.

## SEC-008 hardcoded-secret

**High** for vendor secret formats (AWS `AKIA…`, Stripe `sk_live_`/`rk_live_`,
GitHub `ghp_`/`github_pat_`, Slack `xox?-`, OpenAI-style `sk-…`, Anthropic
`sk-ant-`, Google OAuth `GOCSPX-`, SendGrid `SG.`, Twilio `SK…`, Mapbox
`sk.eyJ`, PEM private keys, a JWT with a non-public role, a literal
`Bearer …`, `user:pass@` URLs). **Medium** for a Google `AIza…` key outside
Firebase options, a Stripe test key, and generic credentials (a secret-named
field assigned a high-entropy literal). **Info** for a Firebase `apiKey` and
an anon/public JWT · detect: script

**Why.** Every string in the binary is recoverable, even with `--obfuscate`.
**Generic credential test:** the name is secret-like, and the value is ≥8
printable ASCII characters with no spaces, not a placeholder (`your_…`,
`xxx`, `changeme`, `<…>`) and not identifier-like (`'access_token'`,
`'Password'`), with mixed letters and digits and entropy ≥3.0 (or ≥20
characters and entropy ≥3.5). Localization files are skipped.

```dart
// Bad
static const clientSecret = 'a8F3…(20 chars)';
// Good: no secret in the app; call your backend (secrets-and-config.md §4)
```

**False positives.** Test fixtures in `lib/` (move them to `test/`). A
public, restricted key the generic test can't recognise: suppress it with
"public, restricted to package X".

## SEC-009 secret-in-build-config

**Low** (Medium for a secret-named value such as `*SECRET*`, `*PRIVATE*`,
`*PASSW*`, `*SERVICE_ROLE*` or `*SIGNING*`, for a literal `defaultValue`, or
for a `.env` file bundled as a Flutter asset) · detect: script
(`String.fromEnvironment('<credential-named>')`, `dotenv.env[…]` /
`dotenv.get(…)`, `@EnviedField`, and `pubspec.yaml` assets listing `.env*` or
a folder that contains one)

**Why.** Build-time config ends up in the binary as plain strings, so it's
config, not a secret store. A bundled `.env` is a plain file at
`flutter_assets/.env` inside the APK or IPA.

```yaml
# Bad
flutter:
  assets:
    - .env
```

**False positives.** A credential-*named* define that holds a public value
(`MAPS_API_KEY` restricted to the app). It's Low on purpose: confirm and
suppress.

## SEC-010 token-in-global-or-ui-state

**Medium** for a public mutable top-level variable or static field, and for
a token in `HydratedBloc` state. **Low** for a private mutable cache, a
`final`/non-literal global, a global provider or observable holding a token,
and a token field in a state or logic class · detect: script

**Why.** Globals are reachable from any code and outlive the session. UI
state shows up in DevTools, `toString`, `Equatable` props and observer logs,
and HydratedBloc writes it to disk.

```dart
// Bad
String? authToken;
final tokenProvider = StateProvider<String?>((ref) => null);
final class AuthSignedIn extends AuthState { final String accessToken; … }

// Good: the session state exposes the user; the token stays in TokenStorage
final class AuthSignedIn extends AuthState { final User user; … }
```

Constants (key names) and `envied` classes are skipped (SEC-008 and SEC-009
own them). Types like `CancelToken`, `RootIsolateToken`, `Object`, keys,
controllers and `FocusNode` are ignored. Overlaps ARCH-105 for mutable
globals.
**False positives.** A private static cache of a secure-storage read (graded
Low: clear it on logout).

## SEC-011 body-logged-in-data-layer

**Low** (Medium in an auth, login, session, token, account, user, profile,
payment, card or OTP file or class) · detect: script (log calls in data-layer
files whose arguments include `response.data`, `res.body`, `request.data`,
`options.data`, `body`, `payload`, `jsonEncode(…)` or `.toJson()`)

**Why.** Bodies carry credentials (login, refresh), personal data (profiles,
messages) and payment details. Log the method, the path, the status and the
duration.

```dart
// Bad
print('login response: ${response.data}');
// Good
log('POST /login → ${response.statusCode}');
```

Not reported when the same call is already SEC-004, or when it's
debug-guarded.
**False positives.** Bodies of public, non-personal data (a public catalogue).
Suppress with the reason.

## SEC-012 release-build-unobfuscated

**Low** · detect: script over CI and build files (`flutter build
apk|appbundle|aab|ipa|ios|macos`, including `\` continuations and argument
lines that follow, skipping `--debug`, `--profile`, `--simulator` and
`--config-only`)

**Why.** `--obfuscate --split-debug-info=<dir>` is the expected release
default. It raises reverse-engineering cost, and the split symbols keep crash
reports readable (`flutter symbolize`). It hides no secrets, which is why
this is Low. The audit skill rates it per risk tier (L1.1, L7.2).

```yaml
- run: flutter build appbundle --release --obfuscate --split-debug-info=build/symbols
```

**False positives.** A build whose flags come from a variable
(`flutter build apk $FLAGS`). Suppress with `# sec-ignore: SEC-012 flags in $FLAGS`.

---

## Calibration notes

Calibrated on lichess-org/mobile (Riverpod), thunder-app/thunder (Bloc),
immich-app/immich `mobile/` (Riverpod), openfoodfacts/smooth-app (Provider)
and KRTirtho/spotube (Riverpod). False positives fixed during calibration:

- Localization getters (`String get error_weakPassword => 'このパスワード…'`)
  read as generic credentials. Now l10n files are skipped, and generic values
  must be printable ASCII.
- `'[name](http://address)'` in translations and `http://local-ip:2283`
  placeholders. Now dotless hosts and l10n files are skipped.
- `request.headers['User-Agent']` in a log. A subscripted `headers` is now
  judged by its key.
- `'has token: ${token.isNotEmpty}'`. Now properties of a secret and
  comparisons aren't values.
- An `Authorization` header in `lib/src/network/socket.dart`, classified as
  logic. Now network, API and client paths count as the data layer.
- `Object? _bindingToken` (an identity token). Now `Object` types and
  `binding`/`action`/`cancellation` qualifiers are skipped.
- `refresh_token` keys were missed because `refresh` was treated as a verb
  prefix. Fixed.
- `notification.body` in a push-handling service. Now only request and
  response bodies count.

Real findings the checker surfaced that scan.sh did not: an access token
interpolated into `log.severe(…)` (scan.sh's `PRV-LOG-LEAK` doesn't match
`log.x` loggers), a JWT column in a plain drift database, and an access token
written to a custom key-value `Store.put`.
