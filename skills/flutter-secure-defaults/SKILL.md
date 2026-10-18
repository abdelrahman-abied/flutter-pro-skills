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

For the common case (store the token, send it, wipe it on logout), the
table above and this source are enough. Write the source in the pattern's
data layer and inject it as the table says:

```dart
class TokenStorage {                       // data/sources/token_storage.dart
  const TokenStorage(this._storage);       // FlutterSecureStorage, injected
  final FlutterSecureStorage _storage;
  static const _key = 'auth_token';
  Future<String?> read() => _storage.read(key: _key);
  Future<void> write(String token) => _storage.write(key: _key, value: token);
  Future<void> clear() => _storage.delete(key: _key);
}
```

Open `references/secure-defaults-by-layer.md` only when you need more than
that: refresh with a single-flight interceptor, multiple tokens, or a pattern's
full session state. Read the section for your pattern, not the whole file.

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

## Reviewing

For a review, read `references/review.md`: the review checklist (every
finding ID with its severity and how to confirm it) and worked finding
examples in the suite's format. Writing code doesn't need it.

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
| `references/review.md` | reviewing: the checklist with every ID, severity and fix, and finding examples |
| `references/secure-defaults-by-layer.md` | writing the token source, the interceptor, the session state and the logout for MVN, MVVM, Bloc, Clean, Provider, GetX or Riverpod |
| `references/network-and-auth.md` | building an HTTP client, login, refresh, TLS settings, timeouts, or response and input validation |
| `references/storage-and-privacy.md` | storing anything, logging, analytics, crash reporting, files and caches (clipboard and screenshots defer to the audit) |
| `references/secrets-and-config.md` | API keys, flavors, `--dart-define`, `.env`/envied, what's public by design, what to do after a leak |
| `references/webview-and-links.md` | WebViews, url_launcher, deep-link input and permissions |
| `references/secure-scaffold-checklist.md` | generating or reviewing feature templates: the rules every scaffolded file follows |
| `references/rules.md` | every SEC-0xx rule (detection, grading, false positives, bad/good code) and the overlap map with `scan.sh` |
