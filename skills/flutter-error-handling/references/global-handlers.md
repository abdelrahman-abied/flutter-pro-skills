# Global error handlers

Global handlers are the last line of defence. They catch what every layer
missed, report it, and keep the app presentable. They are not a substitute for
mapping failures where they happen: a failure that reaches a global handler is
a bug report, not a user message.

From the Flutter docs ("Handling errors in Flutter"):

- The framework catches errors in its own callbacks (build, layout, paint) and
  routes them to `FlutterError.onError`. By default that calls
  `FlutterError.presentError`, which dumps the error to the device log.
- Errors "that don't occur within Flutter's callbacks can't be caught by the
  framework". These include an `onPressed` that awaits a failing
  `MethodChannel.invokeMethod`, a timer, or a stream without `onError`. They go
  to `PlatformDispatcher.instance.onError`, which "by default … only prints
  errors and does nothing else".
- A widget that throws while building is replaced by `ErrorWidget.builder`'s
  output: a red error box in debug, a grey box in release.

## Contents

- What goes where
- Minimal main() (no reporter)
- Firebase Crashlytics
- Sentry
- runZonedGuarded, and the zone mismatch (ERR-013)
- A friendlier ErrorWidget
- Isolates
- State-management observers
- Mistakes to avoid

## What goes where

| Error source | Reaches | Install |
|---|---|---|
| build / layout / paint, gesture and framework callbacks | `FlutterError.onError` | in `main()` |
| async code outside framework callbacks (awaited plugin calls in `onPressed`, timers, futures nobody awaited) | `PlatformDispatcher.instance.onError` | in `main()` |
| everything inside a custom zone | the `runZonedGuarded` handler | optional alternative to `PlatformDispatcher` |
| errors while building a widget | `ErrorWidget.builder` (renders) + `FlutterError.onError` (reports) | `MaterialApp.builder` |
| a spawned `Isolate` | the isolate's error port (not the main handlers) | `Isolate.spawn(..., onError:)` / `addErrorListener` |
| Bloc event handlers | `Bloc.onError` / `BlocObserver.onError` | `Bloc.observer = ...` |
| Riverpod providers | `AsyncError` + `ProviderObserver.providerDidFail` | `ProviderScope(observers: [...])` |

## Minimal main() (no reporter)

This is the docs' "handling all types of errors" shape. Even without a crash
reporter, route both handlers into one logger, so release builds keep a trail.

```dart
import 'dart:ui';

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();

  FlutterError.onError = (details) {
    FlutterError.presentError(details);          // keep the console output in debug
    appLog.error('flutter', details.exception, details.stack);
  };

  PlatformDispatcher.instance.onError = (error, stack) {
    appLog.error('platform', error, stack);
    return true;                                  // handled: don't also run the default
  };

  runApp(const App());
}
```

## Firebase Crashlytics

```dart
Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await Firebase.initializeApp(options: DefaultFirebaseOptions.currentPlatform);

  // Errors caught by the framework (fatal = a crash in the dashboard).
  FlutterError.onError = FirebaseCrashlytics.instance.recordFlutterFatalError;

  // Async errors outside Flutter's callbacks.
  PlatformDispatcher.instance.onError = (error, stack) {
    FirebaseCrashlytics.instance.recordError(error, stack, fatal: true);
    return true;
  };

  // Optional: errors from the main isolate's other entry points.
  Isolate.current.addErrorListener(RawReceivePort((List<dynamic> pair) async {
    await FirebaseCrashlytics.instance.recordError(pair.first, pair.last as StackTrace?, fatal: true);
  }).sendPort);

  // Debug builds shouldn't pollute the dashboard.
  await FirebaseCrashlytics.instance.setCrashlyticsCollectionEnabled(!kDebugMode);

  runApp(const App());
}
```

For failures you *handled* but still want visible, report them as non-fatal
from the boundary that handled them:
`FirebaseCrashlytics.instance.recordError(e, st, reason: 'sync failed')`.
Expected failures (offline, 404) are usually not worth reporting at all.

## Sentry

`SentryFlutter.init` installs the `FlutterError.onError` and
`PlatformDispatcher` integrations itself. Run the app from `appRunner`:

```dart
Future<void> main() async {
  await SentryFlutter.init(
    (options) {
      options.dsn = const String.fromEnvironment('SENTRY_DSN');
      options.environment = const String.fromEnvironment('ENV', defaultValue: 'prod');
    },
    appRunner: () => runApp(const App()),
  );
}
```

If you add your own `FlutterError.onError` after `init`, **chain to the
previous handler**. Otherwise you silently disconnect Sentry:

```dart
final previous = FlutterError.onError;
FlutterError.onError = (details) {
  previous?.call(details);
  appLog.error('flutter', details.exception, details.stack);
};
```

The same applies to any package that installs handlers (Bugsnag, Datadog,
Instabug): read its docs before overwriting what it set.

## runZonedGuarded, and the zone mismatch (ERR-013)

Before `PlatformDispatcher.onError` existed, apps wrapped `runApp` in
`runZonedGuarded`. That still works, but every binding call has to happen
**inside** the zone. The binding remembers the zone it was initialized in, and
calling `runApp` from another zone reports a "Zone mismatch" error.

```dart
// Bad: ensureInitialized runs in the root zone, runApp in the guarded zone
void main() {
  WidgetsFlutterBinding.ensureInitialized();
  runZonedGuarded(() => runApp(const App()), reportError);
}

// Good
void main() {
  runZonedGuarded(() async {
    WidgetsFlutterBinding.ensureInitialized();
    await bootstrap();
    FlutterError.onError = reportFlutterError;
    runApp(const App());
  }, reportError);
}
```

New code doesn't need a zone. `PlatformDispatcher.instance.onError` covers the
same uncaught async errors with less ceremony. Keep `runZonedGuarded` only if
you also need zone features (zone values, a custom `print`).

## A friendlier ErrorWidget

The docs set `ErrorWidget.builder` inside `MaterialApp.builder`, so the
replacement can use the app's theme and directionality:

```dart
MaterialApp(
  builder: (context, widget) {
    Widget error = const Text('...rendering error...');
    if (widget is Scaffold || widget is Navigator) {
      error = Scaffold(body: Center(child: error));
    }
    ErrorWidget.builder = (errorDetails) => error;
    if (widget != null) return widget;
    throw StateError('widget is null');
  },
);
```

Keep the red debug screen in debug builds (`if (kReleaseMode)` around the
assignment) so developers still see the stack. In release, show something
neutral and localized, never `details.exceptionAsString()`.

## Isolates

- `compute(...)` and `Isolate.run(...)` rethrow the isolate's error into the
  awaiting future, so handle them like any other async call.
- A long-lived `Isolate.spawn` worker reports errors only to its `onError`
  port (and exits on an uncaught error unless `errorsAreFatal: false`). Pass
  `onError:` and `onExit:` ports, and forward the error to the owner as a
  message (`Failed('...')`). An unhandled worker error otherwise looks like a
  hang.
- Background handlers (FCM `onBackgroundMessage`, WorkManager tasks) run in
  their own isolate without your `main()` handlers. Wrap their bodies in a
  `try/catch` that reports.

## State-management observers

Use them to *report* unexpected errors in one place. They can't recover state:
the state handling still belongs in the logic layer.

```dart
// Bloc
class AppBlocObserver extends BlocObserver {
  @override
  void onError(BlocBase<dynamic> bloc, Object error, StackTrace stackTrace) {
    reporter.record(error, stackTrace, reason: bloc.runtimeType.toString());
    super.onError(bloc, error, stackTrace);
  }
}
// main(): Bloc.observer = AppBlocObserver();
```

```dart
// Riverpod: providerDidFail receives the unwrapped error.
// Its signature differs between Riverpod 2 and 3: implement the one your version declares.
final class ReportingObserver extends ProviderObserver {
  // Riverpod 3: void providerDidFail(ProviderObserverContext context, Object error, StackTrace stackTrace)
  // Riverpod 2: void providerDidFail(ProviderBase<Object?> provider, Object error, StackTrace stackTrace, ProviderContainer container)
}
// main(): runApp(ProviderScope(observers: [ReportingObserver()], child: const App()));
```

Report a failure in the observer **or** in the logic layer's catch, not both
(ERR-double-report). Expected failures that are mapped to `Failure` usually
skip reporting entirely.

## Mistakes to avoid

- **Only one of the two handlers.** `FlutterError.onError` alone misses every
  async error outside framework callbacks, which is most I/O (ERR-012).
- **Overwriting a reporter's handler** without chaining to `previous`.
- **`exit(1)` in release.** The docs show it as an example of a custom policy.
  Quitting on every framework error is rarely what users want.
- **Showing UI from a global handler.** It has no reliable `BuildContext`. If a
  global failure must reach the user (session expired), publish it to an
  app-level notifier or stream that a top-level widget listens to.
- **Reporting expected failures as fatal.** Offline is not a crash. Map it in
  the repository and show it.
- **Swallowing in the handler** (`PlatformDispatcher.instance.onError = (_, __)
  => true;` with no report). That's ERR-001 at app scale.
