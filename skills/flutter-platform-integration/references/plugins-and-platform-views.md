# Writing plugins and using platform views

Two places where Dart code meets native code in the widget tree or in a
published package. For creating a plugin step by step, follow the
docs.flutter.dev "Developing packages & plugins" guide (or the
`flutter/agent-plugins` recipes if your agent has them).

## Contents

1. Federated plugin layout
2. The platform interface
3. Platform views
4. Review checklist

## 1. Federated plugin layout

| Package | Holds | Depends on |
|---|---|---|
| `battery` (app-facing) | the public API apps call; no platform code | `battery_platform_interface`, the endorsed implementations |
| `battery_platform_interface` | the abstract `BatteryPlatform`, shared data types, and the default `MethodChannelBattery` | `plugin_platform_interface` |
| `battery_android`, `battery_ios`, `battery_web`, … | one implementation per platform, registered with `registerWith()` | `battery_platform_interface` |

- The app-facing package endorses implementations in its `pubspec.yaml`
  (`flutter: plugin: platforms: android: default_package: battery_android`)
  so apps get them without listing them.
- An implementation package declares `implements: battery` and a
  `dartPluginClass` whose static `registerWith()` sets
  `BatteryPlatform.instance = BatteryAndroid()`.
- Breaking changes go in the platform interface only with a major version;
  adding a method is a minor version with a default implementation.
- Prefer Pigeon inside each implementation package: its channels are then
  private to that package and can change freely.

## 2. The platform interface

```dart
import 'package:plugin_platform_interface/plugin_platform_interface.dart';

abstract class BatteryPlatform extends PlatformInterface {
  BatteryPlatform() : super(token: _token);

  static final Object _token = Object();

  static BatteryPlatform _instance = MethodChannelBattery();

  static BatteryPlatform get instance => _instance;

  static set instance(BatteryPlatform instance) {
    PlatformInterface.verify(instance, _token);
    _instance = instance;
  }

  Future<int> level() => throw UnimplementedError('level() has not been implemented.');
}

class BatteryAndroid extends BatteryPlatform {   // extends, not implements
  static void registerWith() => BatteryPlatform.instance = BatteryAndroid();

  @override
  Future<int> level() => _api.level();
}
```

- DO `extends` the platform interface in every implementation (PLAT-009).
  With `implements`, the next minor release that adds a method breaks every
  app using your implementation at compile time; with `extends`, they get the
  default `UnimplementedError` and can handle it.
- DO verify the token in the `instance` setter (PLAT-009, low), so only real
  subclasses are accepted.
- DO give every new method a default body that throws `UnimplementedError`,
  and let the app-facing package turn it into a typed "unsupported" result.
- Test fakes may `implements` the interface, but only with the mixin that
  skips the token check:

```dart
class FakeBatteryPlatform extends Fake with MockPlatformInterfaceMixin implements BatteryPlatform {
  @override
  Future<int> level() async => 42;
}
```

- Inside an app (not a plugin), a platform-interface-style abstraction is
  rarely needed: a repository contract with a channel-backed implementation
  and a fake is enough.

## 3. Platform views

A platform view embeds a native view (`AndroidView`, `UiKitView`,
`AppKitView`, `HtmlElementView` on the web) in the Flutter widget tree. It
is the right tool for maps, web views, ad SDKs and native video players, and
it has a cost on every frame it's visible.

- **Android** offers several composition modes (hybrid composition, texture
  layer hybrid composition, virtual display), chosen through
  `PlatformViewsService` (`initAndroidView`, `initSurfaceAndroidView`,
  `initExpensiveAndroidView`) or by the plugin. They trade correctness of
  native gestures, accessibility and text input against rendering cost and
  Android-version support. Read the docs.flutter.dev "Hosting native Android
  views" page for your Flutter version before choosing, and let the plugin's
  default stand unless you've measured.
- **iOS and macOS** use hybrid composition: the native view is composited
  with Flutter's layers, which adds overhead, especially for content drawn on
  top of the view.
- AVOID platform views per item in scrolling lists, in animated or
  transformed subtrees, or behind blur and opacity effects
  (PLAT-platform-view-in-list). Use one view outside the list, a static
  snapshot (a map image), or a Flutter-native widget.
- Pass gestures deliberately with `gestureRecognizers`; an empty set lets
  Flutter keep the gesture arena.
- Create the native view's controller in a data-layer wrapper or the plugin;
  the widget only hosts it. Dispose it with the widget.
- Measure in profile mode on a low-end device; load `flutter-performance` for
  the timeline and raster-thread diagnosis.

## 4. Review checklist

- implementations `extends` the interface; fakes use
  `MockPlatformInterfaceMixin` (PLAT-009)
- the `instance` setter verifies the token (PLAT-009)
- new interface methods throw `UnimplementedError` by default, and the
  app-facing API maps it
- channel names are private to the implementation package and declared once
  (PLAT-002)
- each implementation maps native errors to the interface's documented
  exceptions; the app-facing package documents which ones apps must catch
- platform views stay out of lists and animations, and their cost was
  measured
- `pubspec.yaml` endorses the implementations and declares
  `implements:` / `dartPluginClass:` correctly
