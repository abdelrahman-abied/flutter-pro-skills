# Flavors and environments

A flavor is a build of the same app with a different identity and
configuration: `dev` talks to a dev backend and installs next to the store
app, `prod` is what ships. Two decisions keep flavors cheap:

1. **One list of flavors**, mirrored on every platform: Android
   `productFlavors`, iOS schemes plus build configurations, and (optionally)
   one `lib/main_<flavor>.dart` each. REL-004 reports drift.
2. **One config object, built at the composition root and injected.** Code
   below the root receives values (`baseUrl`, `sentryDsn`, `showDebugMenu`)
   and never asks which flavor it is in. REL-005 and REL-006 report the two
   ways this goes wrong.

For the step-by-step platform setup, follow the docs.flutter.dev flavors
guides ("Set up flavors for Android" and "for iOS and macOS") and, if your
agent has them installed, the `flutter/agent-plugins` or `dart-lang/skills`
recipes. This file adds the decisions and the per-architecture placement.

## 1. Choosing the mechanism

| Need | Use |
|---|---|
| different app id, name, icon, Firebase project, signing per environment | real flavors (`--flavor dev`) on both platforms |
| only different Dart values (base URL, feature flags) | `--dart-define-from-file=config/dev.json` and a single `main.dart` |
| different Dart wiring per environment (fakes in dev, a mock server) | `lib/main_<flavor>.dart` entrypoints with `-t`, with or without platform flavors |

Combine them freely: `flutter build appbundle --flavor prod -t
lib/main_prod.dart --dart-define-from-file=config/prod.json`.

- **AVOID** `kDebugMode`/`kReleaseMode` as the switch (REL-005). Build mode
  answers "are asserts on and is the code optimised", not "which backend".
  Profile builds exist to measure the release build, and they must be able to
  hit staging.
- **DON'T** put secrets in any of these. `--dart-define` values, JSON define
  files and `.env` assets ship inside the app (SEC-009). A flavor chooses
  *which public config* to use; secrets stay on a server.
- **PREFER** the same flavor names everywhere (`dev`, `staging`, `prod`), so
  `flutter run --flavor staging -t lib/main_staging.dart` reads the same in
  every README, IDE launch config and CI job.

## 2. Android

```kotlin
// android/app/build.gradle.kts
android {
    flavorDimensions += "env"
    productFlavors {
        create("dev") {
            dimension = "env"
            applicationIdSuffix = ".dev"          // installs next to prod
            resValue("string", "app_name", "Shop DEV")
        }
        create("prod") {
            dimension = "env"
        }
    }
}
```

Groovy uses `dev { dimension "env" }` inside `productFlavors`. Per-flavor
`google-services.json` goes in `android/app/src/<flavor>/`.

## 3. iOS

Flutter looks for a scheme named after the flavor and build configurations
named `Debug-<flavor>`, `Release-<flavor>` and `Profile-<flavor>`. Duplicate
the Runner scheme for each flavor (mark it **Shared** so it lands in
`xcshareddata/` and in git), give each configuration its own
`PRODUCT_BUNDLE_IDENTIFIER` (or an xcconfig per flavor) and display name, and
select the per-flavor `GoogleService-Info.plist` in a build phase. App
extensions keep their own schemes; they are not flavors.

## 4. One `AppConfig`, injected per architecture

```dart
// lib/config/app_config.dart
final class AppConfig {
  const AppConfig({required this.flavor, required this.apiBaseUrl, this.showDebugMenu = false});

  factory AppConfig.fromEnvironment() => AppConfig(
        flavor: const String.fromEnvironment('FLAVOR', defaultValue: 'dev'),
        apiBaseUrl: const String.fromEnvironment('API_BASE_URL'),
        showDebugMenu: const bool.fromEnvironment('SHOW_DEBUG_MENU'),
      );

  final String flavor;
  final String apiBaseUrl;
  final bool showDebugMenu;
}
```

The composition root (`main_<flavor>.dart`, `bootstrap.dart`, `app/`, `di/`)
is the only place that reads `appFlavor`, `String.fromEnvironment` or a
flavorizr `F` class (REL-006 exempts it). Everything else receives the value.

| Pattern | Where the config is built | How it reaches the data layer |
|---|---|---|
| MVN (Riverpod codegen) | `main_<flavor>.dart` | `ProviderScope(overrides: [appConfigProvider.overrideWithValue(config)])`; the keepAlive Dio provider in `core/network` reads it; use cases and notifiers never do |
| Riverpod | `main_<flavor>.dart` | same override; only client-building providers `ref.watch(appConfigProvider)` |
| MVVM (Flutter guide) | `main_development.dart` / `main_staging.dart` (compass_app) | the root `MultiProvider` passes it to the API service; view models see repositories only |
| Bloc / Cubit | `main_<flavor>.dart` calls `bootstrap(config)` (VGV layout) | `bootstrap` builds the API client from `config.apiBaseUrl` and provides repositories with `RepositoryProvider`; blocs and widgets never read the flavor |
| Clean Architecture | DI module | `data/datasources/remote` takes the base URL in its constructor; domain knows nothing |
| Provider | `main_<flavor>.dart` | `Provider<AppConfig>.value(value: config)` at the root; services take it by constructor |
| GetX | the initial binding called from `main_<flavor>.dart` | `Get.put(config, permanent: true)`; services read it, controllers don't |
| get_it | `main_<flavor>.dart` before `runApp` | `GetIt.I.registerSingleton<AppConfig>(config)`; resolve only where clients are built |

**UI that depends on the flavor** (a DEV ribbon, a debug menu) gets a boolean
from the config, not the flavor name:

```dart
// Bad (REL-006): a feature branches on the flavor
if (appFlavor == 'prod') return const SizedBox.shrink();

// Good: the root decides, the widget receives a fact
DebugMenuButton(visible: config.showDebugMenu)
```

## 5. Review checklist

- Flavor lists match on Android, iOS and `lib/main_*.dart` (REL-004).
- No environment chosen by build mode (REL-005), no flavor reads below the
  root (REL-006).
- Each flavor has its own application id suffix or bundle id, so dev and prod
  install side by side and never share push tokens or keychains.
- Per-flavor Firebase/Sentry projects, so dev crashes don't page anyone.
- Define files hold only public values (SEC-009 owns secrets).
