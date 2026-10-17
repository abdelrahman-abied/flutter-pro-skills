# FFI: dart:ffi, ffigen, jnigen and native assets

Calling native code directly, without a message channel. FFI calls are
synchronous and run on the calling isolate's thread, which makes them fast
and also makes every mistake (a leak, a long call, a wrong signature) yours.
For setup, follow the dart.dev "C interop" and "Java interop" guides and the
docs.flutter.dev "Binding to native code" guide, or the `dart-lang/skills`
recipes if your agent has them installed.

## Contents

1. Choosing the binding
2. Loading libraries safely
3. Memory ownership
4. Long calls and threads
5. Placement and testing

## 1. Choosing the binding

| Native API | Tool | Notes |
|---|---|---|
| C (your own or a system library) | ffigen from the headers, or `@Native` functions with native assets | generate, don't hand-write `lookupFunction` signatures: a wrong signature corrupts memory instead of failing |
| Objective-C / Swift (Apple frameworks) | ffigen in Objective-C mode with `package:objective_c` | Swift needs an `@objc`-compatible surface |
| Java / Kotlin (Android SDK, AndroidX) | jnigen with `package:jni` | the pedometer sample uses jnigen for Health Connect |
| an async or UI-bound platform API | a channel or Pigeon (`channels-and-pigeon.md`) | FFI doesn't give you the activity or the main thread for free |

Generated bindings (`*_bindings_generated.dart`, jnigen output) are outputs:
configure them in `ffigen.yaml` / `jnigen.yaml`, regenerate, and review the
config and your wrapper, not the generated file. The checker skips them.

## 2. Loading libraries safely

- PREFER native assets with a build hook (`hook/build.dart`) on SDKs that
  support them: the library is built and bundled for each target, and
  `@Native` functions resolve it without a path. Check the guide for your SDK
  version.
- Otherwise open bundled libraries by a constant name:
  `DynamicLibrary.open('libfoo.so')` (Android `jniLibs`, Linux bundle),
  `DynamicLibrary.open('foo.framework/foo')` (iOS/macOS framework),
  `DynamicLibrary.open('foo.dll')` (Windows), or `DynamicLibrary.process()`
  for symbols linked into the app.
- DON'T build the path from `getApplicationDocumentsDirectory()`,
  `getTemporaryDirectory()`, `getApplicationSupportDirectory()`, a downloads
  folder, an environment variable or user input (PLAT-007). Anything the app
  or another process can write there runs with the app's identity. A
  "download a native plugin at runtime" design also breaks store policies.

```dart
DynamicLibrary _open() {
  if (Platform.isAndroid || Platform.isLinux) return DynamicLibrary.open('libtext.so');
  if (Platform.isIOS || Platform.isMacOS) return DynamicLibrary.open('text.framework/text');
  if (Platform.isWindows) return DynamicLibrary.open('text.dll');
  throw UnsupportedError('text is not available on this platform');
}
```

## 3. Memory ownership

The Dart GC doesn't see native memory. Every allocation needs exactly one
owner that frees it (PLAT-006).

**Scoped: an `Arena`.** Everything allocated with the arena is freed when
`using` returns, also on exceptions.

```dart
int measure(String text) => using((arena) {
      final ptr = text.toNativeUtf8(allocator: arena);
      return _measure(ptr);
    });
```

**Scoped by hand: `try`/`finally`.**

```dart
final buffer = calloc<Int32>(values.length);
try {
  for (var i = 0; i < values.length; i++) buffer[i] = values[i];
  return _sum(buffer, values.length);
} finally {
  calloc.free(buffer);
}
```

**Long-lived: a `Finalizable` owner with a `NativeFinalizer`.** The finalizer
frees the memory when the Dart object is collected; give it an explicit
`dispose()` too, so it can be freed deterministically.

```dart
final class NativeBuffer implements Finalizable {
  NativeBuffer(int length) : pointer = calloc<Int32>(length) {
    _finalizer.attach(this, pointer.cast(), detach: this);
  }

  static final _finalizer = NativeFinalizer(calloc.nativeFree);
  final Pointer<Int32> pointer;

  void dispose() {
    _finalizer.detach(this);
    calloc.free(pointer);
  }
}
```

Rules of thumb:

- `toNativeUtf8()` allocates with `malloc` by default. Passing it inline
  (`fn(s.toNativeUtf8())`) always leaks.
- Free with the allocator that allocated (`calloc.free` for `calloc`,
  `malloc.free` for `malloc`).
- Memory returned by a native function is freed by the matching native
  function (`lib_free_string`), not by `calloc.free`, unless the API says
  otherwise.
- jnigen `JObject`s hold JNI global references: `release()` them, or tie
  them to an arena with `releasedBy(arena)`, when they don't live for the
  app's lifetime.
- `NativeCallable` callbacks must be `close()`d when no longer needed, or the
  isolate stays alive.
- Pointers that hold secrets: overwrite the bytes before freeing when the
  value is sensitive.

## 4. Long calls and threads

An FFI call blocks the calling isolate until it returns. On the UI isolate,
anything over a few milliseconds drops frames (PLAT-sync-ffi-on-ui-isolate).

- DO run long synchronous calls (parsing, crypto, image or audio processing,
  disk) in `Isolate.run(() => _bindings.process(bytes))`, or in a long-lived
  worker isolate when you call often. Libraries load per isolate: open the
  `DynamicLibrary` (or use `@Native`) inside the isolate.
- DO use `NativeCallable.listener` for callbacks native code makes from other
  threads; `NativeCallable.isolateLocal` only for synchronous callbacks on
  the same thread.
- Mark `isLeaf: true` only for short calls that never call back into Dart.
- Use `flutter-performance` to confirm with a profile-mode timeline.

## 5. Placement and testing

- The bindings and the wrapper that owns memory live in `data/` (or a
  package), behind a repository or service contract. The domain sees Dart
  types only, never `Pointer`, `Utf8` or `JObject` (PLAT-001).
- Convert at the boundary: native structs become Dart value objects in the
  wrapper, and native error codes become typed exceptions the repository
  maps.
- Test logic against a fake of the repository. Test the wrapper with an
  integration test on a device or desktop host, where the library exists.
  `package:ffi`'s allocators work in unit tests on the host if you build the
  library for it.
