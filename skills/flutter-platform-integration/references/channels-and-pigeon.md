# Platform channels and Pigeon

How to write the Dart side of a channel so it is typed, testable and safe, and
when to let Pigeon write it for you. For step-by-step setup of the native
side, follow the docs.flutter.dev "Writing custom platform-specific code" and
Pigeon guides (or the `flutter/agent-plugins` recipes if your agent has them).

## Contents

1. Choosing a mechanism
2. A hand-written channel wrapper
3. Pigeon
4. Errors and unsupported platforms
5. Threads, codecs and payload size
6. Secure by default

## 1. Choosing a mechanism

| Need | Use | Why |
|---|---|---|
| a few calls Dart → native, simple values | `MethodChannel` in one wrapper class | least ceremony; fine while the API stays small |
| more than one or two methods, structured data, native → Dart calls | **Pigeon** (`@HostApi`, `@FlutterApi`) | typed classes on both sides, no method-name strings, generated code |
| a stream of events from native (sensors, connectivity, downloads) | `EventChannel` (or a Pigeon event channel API on recent Pigeon versions) | the native side starts and stops with the first and last listener |
| raw messages with your own codec (bytes, strings, JSON) | `BasicMessageChannel<T>` | no method envelope |
| a C, Objective-C, Swift or Java/Kotlin API you can call synchronously | `dart:ffi` with ffigen or jnigen (`ffi.md`) | no message hop and no main-thread round trip |
| framework services (clipboard, system navigation, haptics) | `Clipboard`, `SystemNavigator`, `HapticFeedback`, `SystemChannels.*` | already wrapped by Flutter |

PREFER Pigeon as soon as the hand-written wrapper has to parse maps. Pigeon's
whole point is that the compiler checks the contract you would otherwise
check by hand.

## 2. A hand-written channel wrapper

One class per native API, in the data layer. It owns the channel name, the
method names and the decoding, and it's the only code that knows a channel
exists.

```dart
import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';

class BatteryUnsupported implements Exception {
  const BatteryUnsupported();
}

class BatteryPlatformSource {
  BatteryPlatformSource({MethodChannel? channel, EventChannel? events})
      : _channel = channel ?? const MethodChannel(methodChannelName),
        _events = events ?? const EventChannel(eventChannelName);

  static const methodChannelName = 'com.example.app/battery';
  static const eventChannelName = 'com.example.app/battery/charging';

  final MethodChannel _channel;
  final EventChannel _events;

  Future<int> level() async {
    if (kIsWeb) throw const BatteryUnsupported();
    final value = await _channel.invokeMethod<int>('getLevel');
    if (value == null || value < 0 || value > 100) {
      throw PlatformException(code: 'bad-value', message: 'getLevel returned $value');
    }
    return value;
  }

  Stream<bool> get chargingChanges =>
      _events.receiveBroadcastStream().map((event) => event == true);
}
```

- DO keep the channel name in one `static const` (PLAT-002), reverse-domain
  style, and use the same constant in tests.
- DO inject the channel (or the messenger) through the constructor, so tests
  and a second engine (add-to-app) can supply their own.
- DO use the generic forms: `invokeMethod<int>`, `invokeListMethod<String>`,
  `invokeMapMethod<String, Object?>`. They return nullable values: check them
  (PLAT-004). `invokeMethod<Map<String, Object?>>` fails at runtime because
  the codec produces `Map<Object?, Object?>`; use `invokeMapMethod` or
  `Map<String, Object?>.from(...)`.
- DO expose a `Stream` from the source and let the logic own the
  subscription; when the source must listen itself, keep the
  `StreamSubscription` and cancel it in `dispose()` (PLAT-005).
- DO register `setMethodCallHandler` once, in the object that owns the
  channel, and set it to `null` when that owner is disposed (PLAT-008). Only
  one handler per channel name exists per messenger; a second registration
  silently replaces the first.
- AVOID passing `Map<String, dynamic>` argument bags through the app. Give the
  wrapper typed parameters and build the map inside it.

## 3. Pigeon

Pigeon reads a Dart schema and generates the Dart, Kotlin/Java, Swift/ObjC,
C++ or GObject code for both sides.

```dart
// pigeons/messages.dart (committed; the generated files are outputs)
import 'package:pigeon/pigeon.dart';

@ConfigurePigeon(PigeonOptions(
  dartOut: 'lib/src/platform/messages.g.dart',
  dartTestOut: 'test/platform/test_messages.g.dart',
  kotlinOut: 'android/app/src/main/kotlin/com/example/app/Messages.g.kt',
  swiftOut: 'ios/Runner/Messages.g.swift',
))
class BatteryInfo {
  BatteryInfo({required this.level, required this.charging});
  int level;
  bool charging;
}

@HostApi()
abstract class BatteryHostApi {
  @async
  BatteryInfo read();
}

@FlutterApi()
abstract class BatteryEventsApi {
  void onLow(int level);
}
```

Run `dart run pigeon --input pigeons/messages.dart` after every schema
change. Design rules:

- **`@HostApi`** for calls Dart makes; **`@FlutterApi`** for calls native
  makes into Dart (register the Dart implementation once with
  `BatteryEventsApi.setUp(impl)` in a data-layer class, and `setUp(null)` on
  dispose).
- **`@async`** on host methods whose native implementation waits (I/O, a
  system dialog). Without it the native method must return synchronously on
  the platform thread.
- **Task queues** (`@TaskQueue(type: TaskQueueType.serialBackgroundThread)`)
  move slow native handlers off the platform main thread, where supported.
- **Data classes** instead of maps; nullable fields only where the platform
  can really leave them empty. Enums are generated on both sides.
- **Errors**: native code throws the generated error type (`FlutterError` in
  Kotlin, `PigeonError` in Swift on recent versions); Dart receives a
  `PlatformException` with that code. Map it in the repository like any other
  channel error.
- **Generated code is an output.** Keep it out of hand edits and line-level
  review; review the schema. This checker skips the configured `dartOut`
  paths and files with the Pigeon banner.
- Construct the generated `BatteryHostApi()` in the data source (or inject it
  from the composition root). A view or notifier that builds it is PLAT-001.

## 4. Errors and unsupported platforms

| What happens | What Dart sees |
|---|---|
| native calls `result.error(code, message, details)` / throws the Pigeon error | `PlatformException(code, message, details)` |
| no handler for the channel on this platform, in a widget test, or in an uninitialised background isolate | `MissingPluginException` |
| native calls `result.notImplemented()` | `MissingPluginException` |
| native answers `null` or another type | a `null` value, or a `TypeError` when you force it |

- DO catch both exception types in the repository (or the source, when it
  translates them into its own exceptions) and map them to the pattern's
  failure type (PLAT-003). Load `flutter-error-handling` for the mapping and
  for showing it in the UI.
- DO decide platform support in the source, with `kIsWeb` and
  `defaultTargetPlatform` (not `dart:io` `Platform`, which throws on the web),
  and return a typed "unsupported" result or throw a typed exception. The
  platform interface's default implementation of a new method throws
  `UnimplementedError`; treat it the same way.
- AVOID `catch (e) { return null; }` around channel calls; it hides
  `MissingPluginException` in tests and on new platforms (ERR-001).
- In a Dart handler (`setMethodCallHandler`), throw `PlatformException` to
  send an error back, and `MissingPluginException` for an unknown method, so
  the native side gets `notImplemented`.

## 5. Threads, codecs and payload size

- Messages are asynchronous and serialised by a codec on both sides. The
  default `StandardMessageCodec` carries `null`, `bool`, `int`, `double`,
  `String`, typed data (`Uint8List`, `Int32List`, `Int64List`,
  `Float64List`), `List` and `Map`. `JSONMessageCodec`, `StringCodec` and
  `BinaryCodec` exist for `BasicMessageChannel`; `JSONMethodCodec` for method
  and event channels.
- Native handlers run on the platform's main thread by default. Slow native
  work blocks the platform UI; use a background task queue or `@async`.
- Large payloads (images, files) are copied through the codec. Pass a file
  path or use `BinaryCodec`/typed data, not a list of ints, and decode big
  results off the UI isolate (`flutter-performance`).

## 6. Secure by default

- DO validate every value from native at the source: ranges, enum names,
  required keys. Treat it like a server response (PLAT-unvalidated-native-value).
- DON'T send tokens, passwords or whole user records over a channel unless
  the native API needs them; if it does, send only that field, and never log
  the payload (PLAT-sensitive-data-over-channel, SEC-004).
- DON'T accept method names or channel names from user input or deep links.
- Treat incoming `FlutterApi` calls and `setMethodCallHandler` messages as
  untrusted input too: validate arguments before acting on them.
