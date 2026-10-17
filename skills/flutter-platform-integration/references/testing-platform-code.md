# Testing platform code

Test each layer at the seam it owns. Logic and views never need a channel in
their tests: they get a fake repository or source. Only the wrapper that owns
the channel is tested against a mocked messenger, and the native side is
tested on a device. Load `flutter-testing` for which layer to test first and
for fakes versus mocks.

## Contents

1. Logic and views: fake the source or repository
2. Channel wrappers: mock the messenger
3. Event and message channels
4. Pigeon APIs
5. Plugins: fake the platform interface
6. Native behaviour: integration tests

## 1. Logic and views: fake the source or repository

```dart
class FakeBatteryRepository implements BatteryRepository {
  FakeBatteryRepository(this.result);
  Result<int> result;
  @override
  Future<Result<int>> batteryLevel() async => result;
}
```

Override it the pattern's way (a Riverpod `overrideWith`, a constructor, a
`RepositoryProvider`, `Get.put` in a test binding) and test the error path
with `Result.error(BatteryUnsupported())`. If logic can't be tested without
mocking a channel, the channel is in the wrong layer (PLAT-001,
PLAT-no-channel-fake).

## 2. Channel wrappers: mock the messenger

```dart
TestWidgetsFlutterBinding.ensureInitialized();
const channel = MethodChannel(BatteryPlatformSource.methodChannelName);
final messenger = TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;

setUp(() {
  messenger.setMockMethodCallHandler(channel, (call) async {
    switch (call.method) {
      case 'getLevel':
        return 87;
      default:
        throw MissingPluginException();
    }
  });
});

tearDown(() => messenger.setMockMethodCallHandler(channel, null));

test('maps a null answer to an error', () async {
  messenger.setMockMethodCallHandler(channel, (call) async => null);
  expect(BatteryPlatformSource().level(), throwsA(isA<PlatformException>()));
});

test('native error becomes PlatformException', () async {
  messenger.setMockMethodCallHandler(channel, (call) async {
    throw PlatformException(code: 'UNAVAILABLE');
  });
  expect(BatteryPlatformSource().level(), throwsA(isA<PlatformException>()));
});
```

- Use the same constant as production code for the channel name (PLAT-002).
- Cover the answers native code can really give: a value, `null`, a
  `PlatformException`, and no handler at all (`MissingPluginException`).
- In widget tests, `tester.binding.defaultBinaryMessenger` is the same
  messenger.
- Reset every mock handler in `tearDown`; handlers are global to the binding.

## 3. Event and message channels

```dart
messenger.setMockStreamHandler(
  const EventChannel(BatteryPlatformSource.eventChannelName),
  MockStreamHandler.inline(onListen: (arguments, events) {
    events.success(true);
    events.success(false);
    events.endOfStream();
  }),
);
```

For `BasicMessageChannel`, use `setMockDecodedMessageHandler(channel,
(message) async => reply)`. To test a Dart handler registered with
`setMethodCallHandler`, send a message from the "native" side with
`messenger.handlePlatformMessage(name, codec.encodeMethodCall(call), (_) {})`.

## 4. Pigeon APIs

- Inject the generated host API into your source, and pass a fake in tests
  (`class FakeBatteryHostApi implements BatteryHostApi`); the generated class
  is a plain Dart class.
- `dartTestOut` generates a test-side API (`TestBatteryHostApi`) with a
  `setUp(impl)` that installs a mock handler, for testing the generated Dart
  code against your fake native implementation.
- For `@FlutterApi`, call your Dart implementation directly in unit tests; the
  generated `setUp` only routes messages to it.

## 5. Plugins: fake the platform interface

```dart
class FakeBatteryPlatform extends Fake with MockPlatformInterfaceMixin implements BatteryPlatform {
  @override
  Future<int> level() async => 42;
}

setUp(() => BatteryPlatform.instance = FakeBatteryPlatform());
```

`MockPlatformInterfaceMixin` is the only sanctioned way to `implements` a
platform interface (PLAT-009). Test each implementation package's method
channel class with a mocked messenger (section 2).

## 6. Native behaviour: integration tests

Mocks prove the Dart side; they can't prove the native side answers what you
assumed. Run `integration_test` on a device or simulator for each platform
you ship, covering permission prompts (with the OS's test tooling), the
unsupported-platform path, and background isolate use. FFI wrappers can be
tested on the desktop host when the library is built for it.
