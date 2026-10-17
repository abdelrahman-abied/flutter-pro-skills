# Storage and privacy defaults

What may be stored where, and what may leave the device in logs, analytics
and crash reports. Clipboard, screenshots and screen recording, backups,
Keychain accessibility set in native code, and `allowBackup` are the
`flutter-security-audit` skill's checks (L3 and L5: `STO-CLIPBOARD`,
`PLT-NO-FLAGSEC`, `STO-ALLOWBACKUP`, `STO-KEYCHAIN`, `STO-IOS-KEYCHAIN`).
Load it for those (`../flutter-security-audit/SKILL.md`).

## Contents

1. Where each kind of data goes
2. Secure storage done right
3. Databases and Hive
4. Files, caches and sharing
5. Logs
6. Analytics and crash reports
7. Memory and UI state
8. Defer to the audit: clipboard, screenshots, backups

## 1. Where each kind of data goes

| Data | Store | Never |
|---|---|---|
| Access, refresh and ID tokens; session cookies; API credentials; private keys | `flutter_secure_storage` (Keychain / Keystore) through one data-layer source | SharedPreferences, GetStorage, plain Hive, drift/sqflite, files, state, globals |
| The key that encrypts a local database or Hive box | `flutter_secure_storage` | next to the database, in source, in `--dart-define` |
| User data you must cache (messages, orders, health) | an encrypted database (SQLCipher via `sqlcipher_flutter_libs`, or a Hive box with `HiveAesCipher`) | plain files on external storage |
| Non-sensitive preferences (theme, locale, onboarding seen) | SharedPreferences | anything that identifies or authenticates the user |
| Passwords | **nowhere.** Exchange them for tokens and forget them | anywhere, including secure storage. Saving a password to auto-relogin is a server design problem |

SharedPreferences is an XML file on Android and a plist on iOS: readable
with `adb backup` on older Android, on any rooted or jailbroken device, and
from unencrypted device backups. GetStorage writes plain JSON. That's why the
checker grades a token there High (SEC-001).

## 2. Secure storage done right

```dart
const secureStorage = FlutterSecureStorage(
  iOptions: IOSOptions(accessibility: KeychainAccessibility.first_unlock_this_device),
);
```

- Wrap it in **one** class (`TokenStorage`, see `secure-defaults-by-layer.md`
  §1.1). Nobody else calls `FlutterSecureStorage` for credentials.
- `first_unlock_this_device` keeps items off iCloud Keychain sync and makes
  them unreadable before the first unlock after boot. If you need background
  refresh before first unlock, decide that consciously.
- Use the package's current Android defaults. Don't copy options from old
  blog posts without checking the version you're on.
- The **iOS Keychain survives uninstall.** Clear it on the first launch after
  install (`clearKeychainOnFreshInstall` in the by-layer file), or a
  reinstall starts signed in.
- Secure storage reads can throw (`PlatformException` after a backup restore
  onto another device, Keystore key invalidation). Catch at the source, treat
  it as "signed out", and `deleteAll()` so the next login works.

## 3. Databases and Hive

- A `jwt`, `token` or `password` column in drift or sqflite is plain text on
  disk (SEC-001 reports it once per file). Keep the token in secure storage
  and the account row in the database, or encrypt the database with SQLCipher
  and keep its key in secure storage.
- Hive: open sensitive boxes with `encryptionCipher: HiveAesCipher(key)`,
  where `key` comes from secure storage. The checker grades Hive puts Low
  when the project uses `encryptionCipher` anywhere, because it can't tell
  which box you opened with it. Confirm it.
- `isar`/`objectbox` aren't encrypted by default either. The same rule
  applies.
- On logout, delete or clear user databases and boxes (`SEC-no-logout-wipe`).

## 4. Files, caches and sharing

- Write private files to `getApplicationSupportDirectory()` or
  `getApplicationDocumentsDirectory()` (the app sandbox). Never write them to
  `getExternalStorageDirectory()`, Downloads or a shared folder unless the
  user asked to export them (`SEC-sensitive-file-exposure`).
- Exports for `share_plus` go to a temp file you delete after sharing.
- `cached_network_image` and HTTP caches store responses on disk. Don't
  cache private images or authenticated responses beyond the session, and
  clear the caches on logout.
- Use the photo and file pickers instead of broad storage permissions (see
  `webview-and-links.md` §4).
- Clean up temp files: decrypted PDFs, camera captures and recordings.

## 5. Logs

Logs leave the device more often than people think: crash-reporter
breadcrumbs, support "send logs" buttons, `adb logcat` on a lost phone, and
bug reports pasted into public trackers. `print` and `debugPrint` **run in
release builds**. `dart:developer`'s `log()` is silent in release builds.

**Rules:**
- Log events and identifiers you'd be happy to see in a public issue:
  `signed in (user 4f2a…)`, `GET /orders → 200 (120 ms)`.
- Never log tokens, passwords, `Authorization` or `Cookie` values, request or
  response bodies, or personal data (SEC-004, SEC-011). Form-field values are
  `flutter-forms` FORM-004 (see the `flutter-forms` skill,
  `../flutter-forms/SKILL.md`).
- Gate verbose and HTTP logging with `kDebugMode` (SEC-005). The `logger`
  package's default filter already drops logs in release. Custom `Talker` or
  `logging` setups need an explicit level.
- Turn on the `avoid_print` lint, and route everything through one logger
  that redacts.

```dart
/// Masks a secret for logs and reports: keeps a short prefix and the length.
String redact(String? value) {
  if (value == null || value.isEmpty) return '<empty>';
  final keep = value.length < 16 ? 1 : 4;
  return '${value.substring(0, keep)}…(${value.length} chars)';
}

log('refreshed token ${redact(access)}');   // refreshed token eyJh…(612 chars)
```

## 6. Analytics and crash reports

These are third-party data processors, so treat every call as data you
publish. The checker grades secrets in analytics and crash calls **High**
(SEC-004).

- **User identity:** use an opaque, app-scoped ID (`setUserIdentifier(uuid)`),
  never an email, phone number or username.
- **Sentry:** keep `options.sendDefaultPii = false` (the default) and scrub in
  `beforeSend` and `beforeBreadcrumb` (drop `Authorization`, cookies and
  bodies). Turn off automatic HTTP breadcrumbs for authenticated clients, or
  scrub them.
- **Crashlytics:** `log()`, `setCustomKey()` and `recordError(…, reason:)`
  are uploaded. Never put form values, tokens or full URLs with query strings
  there.
- **Analytics events:** event parameters describe *what* happened
  (`{'method': 'password'}`), never *who* or *with what secret*.
- **Error messages** shown to users must be user-safe and must not echo
  internals (`flutter-error-handling`, ERR-008).
- Honour consent: initialise analytics after consent where the law requires
  it, and offer an opt-out. Don't send events from a signed-out kiosk mode
  with a previous user's ID.

## 7. Memory and UI state

- UI state is visible in DevTools, in `toString()` and `Equatable` props, in
  `BlocObserver.onChange` and `ProviderObserver` logs, and in widget-test
  golden failures. Keep tokens out of it (SEC-010).
- `HydratedBloc` writes state to disk. Never hydrate credentials, or pass
  `HydratedAesCipher` with a key from secure storage.
- A login form may hold the password while the user types. Clear the
  controller after submit, and don't keep it in a long-lived provider.

## 8. Defer to the audit: clipboard, screenshots, backups

The audit skill owns these, because they're platform configuration rather
than everyday code:

| Topic | Audit check | Write-time default you can still apply |
|---|---|---|
| Copying secrets to the clipboard | `STO-CLIPBOARD` | don't offer "copy" on tokens, OTPs or recovery codes; if you must, clear it after a timeout |
| Screenshots and app-switcher previews | `PLT-NO-FLAGSEC`, `PLT-ISCAPTURED` | mark sensitive screens so the platform code can protect them |
| Auto-backup of app data | `STO-ALLOWBACKUP` | keep secrets in secure storage, which isn't restored to a new device the same way |
| Keychain accessibility in native code | `STO-IOS-KEYCHAIN` | use `first_unlock_this_device` from Dart |
| Weak randomness for tokens and nonces | `CRY-WEAK-RANDOM` | `Random.secure()`, never `Random()` |
