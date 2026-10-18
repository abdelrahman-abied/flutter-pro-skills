# flutter-platform-integration: review checklist and finding examples

Moved out of `SKILL.md` so writing code doesn't load it: read this file
when you review code in this area, or when `dart-flutter-review` sends
you here. Paths are relative to the skill folder.

## REVIEW checklist

Script rules (`PLAT-0xx`, full detail in `references/rules.md`):

| ID | Name | Default severity | What it catches |
|---|---|---|---|
| PLAT-001 | channel-outside-data-layer | Medium (Low when the app has no data layer) | a channel, `invokeMethod`, Pigeon API, `DynamicLibrary` or native allocation in a widget/State or logic class |
| PLAT-002 | channel-name-duplicated | Low | the same channel name literal in several places |
| PLAT-003 | platform-call-unhandled | Low | `invokeMethod` whose `PlatformException` nobody on its path catches |
| PLAT-004 | platform-result-force-unwrapped | Low | `result!` or a non-nullable `as T` on an `invokeMethod` result |
| PLAT-005 | event-subscription-dropped | Medium (Low outside UI/logic) | `receiveBroadcastStream().listen(...)` whose subscription is discarded |
| PLAT-006 | native-memory-not-freed | High | `calloc`/`malloc`/`toNativeUtf8()` with no free, Arena, finalizer or owner |
| PLAT-007 | library-loaded-from-writable-path | High | `DynamicLibrary.open` of a path from a writable directory, the environment or user input |
| PLAT-008 | call-handler-never-cleared | Low | a State or logic class that never clears its call/message handler |
| PLAT-009 | platform-interface-not-enforced | Medium (Low for the setter) | `implements` a `PlatformInterface`, or an `instance` setter without `verify` |
| PLAT-010 | isolate-channel-without-messenger | High | an isolate entry point using channels or plugins without `BackgroundIsolateBinaryMessenger.ensureInitialized` |
| PLAT-011 | permission-requested-at-startup | Low | `Permission.x.request()` in `main()`/`bootstrap()` |
| PLAT-012 | permanent-denial-unhandled | Low | permission requests in an app that never handles `permanentlyDenied` |

Reading-level findings (`PLAT-<slug>`; the checker can't see these):

| ID | Severity | Look for |
|---|---|---|
| PLAT-unvalidated-native-value | Medium | values from native used without range, enum or shape checks |
| PLAT-sensitive-data-over-channel | Medium | tokens, passwords or whole user records sent to native code that doesn't need them |
| PLAT-sync-ffi-on-ui-isolate | Medium | a long synchronous FFI call in `build()`, a UI callback or a frame callback |
| PLAT-platform-view-in-list | Medium | `AndroidView`/`UiKitView`/`HtmlElementView` built per list item or animated |
| PLAT-handwritten-channel-api | Low | a growing hand-written channel API (string method names, `Map` arguments) where Pigeon fits |
| PLAT-platform-check-in-widget | Low | `Platform.isX`/`kIsWeb` branches in widgets deciding whether a native call works. Now automated as `ADAPT-001`/`ADAPT-002` (`flutter-adaptive-layout`); report the ADAPT id |
| PLAT-generated-code-edited | Low | hand edits in Pigeon/ffigen/jnigen output, or generated files reviewed as source |
| PLAT-no-channel-fake | Low | logic tested against the real engine because the channel can't be injected |

**Don't report here (cross-reference instead):**
- HTTP or database I/O in widgets and logic: ARCH-005/007/101; generic
  swallowed or untyped catches: ERR-001/002/003; unguarded network I/O in UI
  callbacks: ERR-014. PLAT-003 covers only the channel-specific
  `PlatformException`/`MissingPluginException` path.
- Which permissions to ask for, secrets and tokens in storage or logs:
  `flutter-secure-defaults` (SEC-001/004, SEC-permission-overreach; PLAT-011
  automates the startup case). iOS usage strings: REL-009.
- Heavy Dart work on the UI isolate: PERF-011 (PLAT owns only synchronous FFI
  calls). Platform-view cost in lists: `flutter-performance`.
- Undisposed controllers and assigned subscriptions: UI-lifecycle and the
  `undisposed-resource` heuristic. PLAT-005 owns only the discarded
  `receiveBroadcastStream().listen` result and beats the heuristic on the
  same line.

**When not to flag:**
- A `static const` channel inside a small wrapper class, even in a file
  under `ui/` (the wrapper is the data source).
- `SystemChannels.*` calls (framework channels such as
  `SystemNavigator.pop`).
- A Pigeon API or channel built in `main()` or a DI module and injected.
- A Riverpod keepAlive provider in `core/` or `data/` that reads a channel:
  that is the app's data provider.
- Plugin implementation methods marked `@override`: their callers go through
  the platform interface, and the app maps the error.

## Finding examples

Use the suite's finding format (`dart-flutter-review` merges them):

```markdown
### [HIGH] UTF-8 strings leak on every call
- id: PLAT-006
- where: lib/core/native/core_library.dart:22
- evidence: `return fn(workDir.toNativeUtf8(), secret.toNativeUtf8());`
- rule: free every native allocation (flutter-platform-integration › rules.md PLAT-006)
- why: toNativeUtf8() allocates with malloc and nothing keeps the pointer, so each call leaks two strings (and the secret stays in native memory)
- fix: |
    return using((arena) => fn(workDir.toNativeUtf8(allocator: arena), secret.toNativeUtf8(allocator: arena)));
- confidence: confirmed

### [MEDIUM] EventChannel listened to from a State and never cancelled
- id: PLAT-005
- where: lib/features/battery/presentation/view/battery_view.dart:23
- evidence: `const EventChannel('app.example/charging').receiveBroadcastStream().listen(...)` in initState
- rule: keep and cancel the subscription; move the stream into a source (flutter-platform-integration › rules.md PLAT-005, PLAT-001)
- why: the native listener keeps running after the screen closes and setState runs on a disposed State
- fix: |
    _sub = source.chargingChanges.listen(...);   // in the notifier, cancelled in ref.onDispose
- confidence: confirmed
```

Open the report with one line naming the profile and the interop in use
(`mvn, 2 Pigeon APIs + 1 FFI library`). Report a pattern-wide issue (for
example, no repository maps `PlatformException`) **once**, with a few
locations.
