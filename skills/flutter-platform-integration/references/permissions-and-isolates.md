# Runtime permissions and background isolates

Two platform concerns that cut across features: asking the user for access,
and talking to the platform from an isolate other than the root one.
Which permissions to ask for, and the manifest and usage-string side, belong
to `flutter-secure-defaults` (minimal permissions) and `flutter-release`
(REL-009 iOS usage descriptions).

## Contents

1. When to ask
2. The permission service
3. Every status, handled
4. Placement per pattern
5. Background isolates
6. Code that runs when the app isn't open

## 1. When to ask

- DO ask at the moment of use: when the user taps "Scan", "Attach photo" or
  "Find stores near me", not in `main()` or on the first screen (PLAT-011).
  The context makes the system prompt make sense, and a denial affects only
  that feature.
- DO show a short rationale first when the platform says it helps
  (`shouldShowRequestRationale` on Android) or when the permission is
  sensitive (location, contacts, microphone).
- DO ask for the narrowest permission: `locationWhenInUse` before
  `locationAlways`, photo picker flows before full photo-library access, no
  storage permission for app-private files.
- DON'T ask again in a loop. After a permanent denial, the only path is the
  app settings.

## 2. The permission service

Wrap `permission_handler` (or the plugin's own permission API) in one service
in the data layer, and return a domain value instead of `PermissionStatus`,
so logic and tests don't depend on the plugin.

```dart
enum CameraAccess { granted, denied, blocked }

class PermissionService {
  Future<CameraAccess> cameraStatus() async => _map(await Permission.camera.status);

  Future<CameraAccess> requestCamera() async => _map(await Permission.camera.request());

  Future<bool> openSettings() => openAppSettings();

  CameraAccess _map(PermissionStatus status) => switch (status) {
        PermissionStatus.granted || PermissionStatus.limited => CameraAccess.granted,
        PermissionStatus.permanentlyDenied || PermissionStatus.restricted => CameraAccess.blocked,
        _ => CameraAccess.denied,
      };
}
```

Permissions are the one place where the view starts a platform interaction:
the request shows a system dialog over the current screen, so the user's tap
triggers it. The logic decides *whether* to ask (feature state, rationale
shown), the service performs it, and the view renders the result.

## 3. Every status, handled

| Status | Meaning | UI |
|---|---|---|
| granted / limited | access (limited: a subset, iOS photos) | continue; offer "select more" for limited |
| denied | the user said no this time; asking again shows the prompt | explain why, offer to ask again |
| permanentlyDenied | the OS won't show the prompt again | explain, and offer `openAppSettings()` (PLAT-012) |
| restricted | parental controls or MDM block it | explain; no settings link helps |
| provisional | iOS provisional notifications | treat as granted, quietly |

Re-check the status when the app resumes (`AppLifecycleState.resumed`): the
user may have changed it in Settings.

## 4. Placement per pattern

| Pattern | Service | Who decides when | Who shows the result |
|---|---|---|---|
| MVN | `data/sources/permission_source.dart` + a use case returning `CameraAccess` | the notifier, on a user intent | the view, from the notifier's state |
| MVVM | `data/services/permission_service.dart` | the view model's `Command` | the view |
| Bloc | a `PermissionRepository` (or client package) via `RepositoryProvider` | the bloc, on an event | `BlocBuilder`/`BlocListener` |
| Clean | a data source + repository; the domain owns `CameraAccess` | the use case | the presentation layer |
| Provider / GetX / Riverpod | a service (root `Provider`, `GetxService`, a provider) | the ChangeNotifier / controller / notifier | the view |

## 5. Background isolates

Platform channels need the root isolate's binary messenger. Since Flutter
3.7, a spawned isolate can use it after initialising it with the root
isolate's token (PLAT-010):

```dart
Future<void> exportAll(List<String> ids) async {
  final token = RootIsolateToken.instance!;          // only valid on the root isolate
  await Isolate.run(() async {
    BackgroundIsolateBinaryMessenger.ensureInitialized(token);
    final dir = await getApplicationDocumentsDirectory();   // plugins work from here on
    // ...
  });
}
```

- `RootIsolateToken.instance` is `null` inside the spawned isolate: read it
  on the root isolate and pass it in.
- Call `ensureInitialized` before any plugin call in that isolate, including
  `SharedPreferences`, `path_provider` and your own channels.
- The plugin has to support background isolates; plugins that need the
  current activity or the main thread (UI, permission prompts) don't work
  there. Do those on the root isolate and pass the result in.
- An isolate that used platform channels may not exit on its own; use
  `Isolate.run` for one-off work, or close long-lived isolates explicitly.
- Heavy Dart work that doesn't need the platform belongs in `Isolate.run`
  too, without the messenger (`flutter-performance`).

## 6. Code that runs when the app isn't open

Background execution plugins (work managers, background fetch, push
handlers) start a separate engine and call a top-level or static entry point.

- Mark it `@pragma('vm:entry-point')` so tree shaking keeps it in release
  builds.
- Initialise only what the task needs (no `runApp`, no UI); plugins used
  there must support headless execution.
- Keep the data layer usable without the widget tree: the same repository
  and sources, built by a small composition function the entry point calls.
