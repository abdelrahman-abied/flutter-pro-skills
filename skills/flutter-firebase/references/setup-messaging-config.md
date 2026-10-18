# Setup, emulators, messaging, Crashlytics, Analytics, Remote Config, Functions

Step-by-step project setup (installing the FlutterFire CLI, `flutterfire
configure`, the platform files) is in firebase.google.com/docs/flutter and
the FlutterFire docs; defer to them, or to the official `flutter/agent-plugins`
and `dart-lang/skills` recipes if your agent has them installed. This file
covers what those guides leave to you: where each call goes, in what order,
and what must never ship.

## Contents

1. Initialisation order
2. One Firebase project per flavor
3. Emulators, debug only
4. Cloud Messaging (FCM)
5. Crashlytics and Analytics
6. Remote Config
7. Cloud Functions callables

## 1. Initialisation order

```dart
Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();                                       // 1. binding (platform channels)
  await Firebase.initializeApp(options: DefaultFirebaseOptions.currentPlatform);   // 2. once, awaited
  await FirebaseAppCheck.instance.activate(/* production providers, debug in kDebugMode */);  // 3.
  if (kDebugMode && useEmulators) await connectEmulators();                         // 4. before first use
  FirebaseMessaging.onBackgroundMessage(firebaseMessagingBackgroundHandler);        // 5. top-level handler
  // 6. global error handlers -> Crashlytics (flutter-error-handling, ERR-012)
  runApp(const ProviderScope(child: App()));                                        // 7.
}
```

- FIRE-005 reports a missing `await`, `runApp` first, or `initializeApp`
  before `ensureInitialized()`.
- Call `initializeApp` once. A background isolate (the FCM handler, a
  `WorkManager` task) is a new isolate and calls it again itself.
- With `runZonedGuarded`, do steps 1–7 inside the same zone (ERR-013).
- Slow start-up: keep `initializeApp` awaited, but start independent work in
  parallel with `Future.wait([...])`.

## 2. One Firebase project per flavor

- One Firebase project per environment (dev, staging, prod), so test data,
  rules experiments and quotas never touch production.
- Generate one options file per project:
  `flutterfire configure --project=my-app-dev --out=lib/firebase_options_dev.dart
  --android-package-name=com.example.app.dev --ios-bundle-id=com.example.app.dev`.
- Each `main_<flavor>.dart` imports its own options file; nothing below the
  composition root knows the flavor (REL-006). Platform files
  (`google-services.json`, `GoogleService-Info.plist`) go in the flavor's
  source set or scheme (`flutter-release`).
- The options files hold identifiers, not secrets; committing them is
  normal. Restrict the API keys in Google Cloud (by app signature and bundle
  id) and rely on rules and App Check.

## 3. Emulators, debug only

```dart
const useEmulators = bool.fromEnvironment('USE_EMULATORS');   // flutter run --dart-define=USE_EMULATORS=true

Future<void> connectEmulators() async {
  final host = !kIsWeb && defaultTargetPlatform == TargetPlatform.android ? '10.0.2.2' : 'localhost';
  FirebaseFirestore.instance.useFirestoreEmulator(host, 8080);
  await FirebaseAuth.instance.useAuthEmulator(host, 9099);
  FirebaseFunctions.instance.useFunctionsEmulator(host, 5001);
  await FirebaseStorage.instance.useStorageEmulator(host, 9199);
}
```

- Call it only under `kDebugMode` (or from `main_dev.dart`), before any
  other use of those products (FIRE-004). A hand-set `const useEmulator =
  true` isn't a guard.
- A physical device needs the host machine's LAN address and
  `firebase emulators:start --host 0.0.0.0`-style config in `firebase.json`.
- Use a `demo-*` project id for emulator-only work: a demo project has no
  real backend, so a call that misses an emulator fails instead of reaching
  production.

## 4. Cloud Messaging (FCM)

```dart
@pragma('vm:entry-point')
Future<void> firebaseMessagingBackgroundHandler(RemoteMessage message) async {
  await Firebase.initializeApp(options: DefaultFirebaseOptions.currentPlatform);
  // No UI, no providers from the main isolate: write to local storage or show a local notification.
}
```

- The background handler is a top-level or static function with
  `@pragma('vm:entry-point')` (FIRE-006).
- Ask for permission when the user turns notifications on, not at launch
  (`requestPermission()`; PLAT-011), and handle denial, including "denied
  forever" on iOS and Android 13+ (PLAT-012).
- Token lifecycle, in a messaging source behind a repository:
  `getToken()` after sign-in, `onTokenRefresh` → send to your backend
  (`flutter-networking`), `deleteToken()` on sign-out
  (FIRE-token-refresh-ignored). Tie the token to the user on the server, not
  in a client-writable document field the rules don't check.
- Foreground messages (`onMessage`), taps (`onMessageOpenedApp`,
  `getInitialMessage()`) go through the logic layer as events; navigation
  from a tap belongs to `flutter-navigation` (validate the route data, it
  comes from outside).
- Payloads: send ids, not content. No emails, names, tokens or message text
  in `data` (FIRE-pii-in-push-payload); the notification is visible on the
  lock screen and in system logs.
- Listeners to `onMessage` in a `State` or a bloc are cancelled with it
  (FIRE-008); app-wide ones live in `main()` or an app-lifetime service.

## 5. Crashlytics and Analytics

- Wiring the global handlers (`FlutterError.onError =
  FirebaseCrashlytics.instance.recordFlutterFatalError`,
  `PlatformDispatcher.instance.onError`) belongs to `flutter-error-handling`
  (ERR-012). Collect only in release:
  `setCrashlyticsCollectionEnabled(!kDebugMode)`.
- No PII, tokens or field values in custom keys, logs, user ids or Analytics
  events and parameters (SEC-004, FORM-004). `setUserIdentifier` takes an
  opaque id, never an email.
- Wrap Analytics in an analytics repository or service in the data layer,
  so logic logs domain events (`checkoutStarted`) and the mapping to event
  names lives in one place; blocs often report through a `BlocObserver`.
- Respect consent: `setAnalyticsCollectionEnabled(false)` until the user
  agrees where the law requires it.

## 6. Remote Config

```dart
final rc = FirebaseRemoteConfig.instance;
await rc.setConfigSettings(RemoteConfigSettings(
  fetchTimeout: const Duration(seconds: 10),
  minimumFetchInterval: kDebugMode ? Duration.zero : const Duration(hours: 1),
));
await rc.setDefaults(const {'welcome_message': 'Welcome', 'new_checkout_enabled': false});
await rc.fetchAndActivate();
```

- Remote Config is public to every client: no API keys, secrets or tokens
  (FIRE-009), and no security decisions (`is_admin`, `role`): the client can
  be made to see any value. It is for tuning, copy and gradual rollouts.
- Defaults live in code (`setDefaults`) so the first launch offline behaves
  (FIRE-remote-config-no-defaults).
- Read it in a data source behind a feature-flags repository; logic asks
  `isNewCheckoutEnabled()`, not `getBool('new_checkout_enabled')`.
- Real-time updates (`onConfigUpdated.listen`) are a subscription like any
  other: owned and cancelled (FIRE-008), followed by `activate()`.

## 7. Cloud Functions callables

```dart
// data source
Future<String> createInvite(String teamId) async {
  final result = await _functions.httpsCallable('createInvite').call<Map<String, Object?>>({'teamId': teamId});
  final code = result.data['code'];
  if (code is! String) throw const FormatException('createInvite: no code');
  return code;
}
// repository: on FirebaseFunctionsException catch (e) -> switch (e.code) { 'permission-denied' => ..., 'unavailable' => ... }
```

- The function checks `request.auth` and validates every input; it never
  trusts a `uid` or role sent in `data` (FIRE-callable-trusts-client).
  Enforce App Check on callables (`enforceAppCheck: true`).
- Secrets that a third-party API needs live in the function's secret
  manager config, never in the app or Remote Config.
- Map `FirebaseFunctionsException.code` to failures in the repository
  (ERR-004); `details` may carry server data, not user-facing text.
- Set a timeout (`HttpsCallableOptions(timeout: ...)`) for long calls, and
  make retried calls idempotent (an idempotency key in `data`).
