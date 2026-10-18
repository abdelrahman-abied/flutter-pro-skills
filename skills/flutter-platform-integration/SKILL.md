---
name: flutter-platform-integration
description: Write and review Flutter code that talks to native code, clean and secure by default and placed by the app's own architecture. Covers MethodChannel, EventChannel and BasicMessageChannel (one constant name, typed wrappers), Pigeon HostApi and FlutterApi, dart ffi with ffigen, jnigen and native assets (calloc and free, Arena, NativeFinalizer, Isolate.run), platform views, federated plugins and PlatformInterface, permissions, background isolates with BackgroundIsolateBinaryMessenger, PlatformException and MissingPluginException, and channel mocks in tests. Ships a PLAT checker. Use it whenever code adds a channel, Pigeon file, FFI binding, plugin, platform view or permission request, even if nobody says "platform". For failure mapping load flutter-error-handling, for permission and secrets policy flutter-secure-defaults, for usage strings flutter-release, for test strategy flutter-testing.
license: MIT
metadata:
  author: abdelrahman-abied
  version: "1.6.1"
  suite: flutter-pro-skills
---

# Flutter platform integration

Native interop fails in ways Dart code usually doesn't. A typo in a channel
name throws `MissingPluginException` only on the device that hits it, a
`result!` crashes when the native side answers `null`, an `EventChannel`
listener keeps the sensor running after the screen closed, a `toNativeUtf8()`
passed straight into a call leaks on every call, and a library opened from the
documents folder runs whatever someone wrote there. This skill writes
platform code that is correct for the architecture the project already uses
and safe without a later hardening pass.

The core split holds in every pattern:

- **A channel or FFI binding is a data source.** It lives in `data/` (or in a
  plugin package) behind a repository or service contract, with one constant
  channel name and typed methods. Views and logic (MVN notifiers, MVVM view
  models, blocs, GetX controllers) never touch a channel or a pointer.
- **The repository maps errors.** `PlatformException` and
  `MissingPluginException` become a typed failure there, never in a widget.
- **Prefer Pigeon** over hand-written channels for anything beyond one or two
  calls: typed messages on both sides, no string method names, generated
  code you never edit or review.
- **Native memory has an owner.** Every allocation is freed by an `Arena`, a
  `finally`, or a `NativeFinalizer`. Long synchronous native calls run in
  `Isolate.run`.
- **Secure by default:** validate every value that comes back from native at
  the source boundary, send the minimum over a channel (no tokens unless the
  native side needs them), never load a library from a writable path, and
  request permissions only at the moment of use.

## Workflow

### 1. Detect the architecture and the interop in use

Check your agent's project instructions file (`AGENTS.md`, `CLAUDE.md`,
`GEMINI.md`, `.cursor/rules/…`, `.github/copilot-instructions.md`) for a
declared pattern. A declared convention wins. Then run the checker. It is
read-only, uses only the Python standard library, and doesn't need `pub get`:

```bash
python3 -I <skill-dir>/scripts/check_platform.py <project-root>                   # text report
python3 -I <skill-dir>/scripts/check_platform.py <project-root> --json            # schema flutter-pro-skills/platform@1
python3 -I <skill-dir>/scripts/check_platform.py <project-root> --files changed.txt  # diff review
python3 -I <skill-dir>/scripts/check_platform.py <project-root> --profile bloc    # declared pattern wins
```

The CLI is `check_platform.py <project-root> [--json] [--files
<list-file-or-comma-list>] [--profile auto|mvn|mvvm|bloc|mvc|getx|provider|riverpod|setstate]
[--max n]`. It exits `0` whenever a report is produced and `2` on a usage
error. It reads the profile and file roles from the `flutter-architecture`
checker (`../flutter-architecture/scripts/arch_check.py --json`, or
`$FPS_ARCH_JSON` when the review already ran it). If that sibling is missing,
it falls back to path-based detection and says so on the `classification:`
line. Generated Pigeon, ffigen and jnigen output is skipped by banner and by
the output paths configured in `pigeons/*.dart`, `ffigen.yaml` and
`jnigen.yaml`.

```text
== PLATFORM
  profile: mvn + clean (arch_check, confidence high)
  classification: arch_check files[]
  scanned: 96 files (4 generated skipped); channels: 3 method, 1 event, 0 message; 2 Pigeon APIs; 1 FFI file, 3 native allocations; ...
  [PLAT-006] native-memory-not-freed (high) x1 — Native memory is allocated with calloc/malloc or toNativeUtf8() and never freed ...
      lib/core/ffi/native_text.dart:17  final pointer = text.toNativeUtf8();   [`pointer` (toNativeUtf8) is never freed in measure(). ...]
```

### 2. Place each piece by the pattern

| Piece | MVN | MVVM | Bloc / Cubit | Clean | Provider | GetX | Riverpod |
|---|---|---|---|---|---|---|---|
| channel / Pigeon / FFI wrapper | `data/sources/<x>_platform_source.dart` | `data/services/` | data-provider class or plugin package | `data/datasources/` | service built at the root | `GetxService` in the initial binding | source + its provider |
| `PlatformException` mapping | repository impl → `Failure` | repository → `Result.error` | repository → failure | repository impl (`Either`) | repository | repository | repository provider or `AsyncValue.error` |
| event stream lifetime | `ref.onDispose` | `dispose()` | `close()` | the logic layer's | `dispose()` | `onClose()` | `ref.onDispose` |
| permission request | permission source + use case; the view asks | service; view model exposes status | permission repository; bloc state | source + use case | service | service | service provider |

Read `references/placement-by-architecture.md` for the layouts per pattern,
`references/channels-and-pigeon.md` before writing a channel or a Pigeon
file, `references/ffi.md` before touching `dart:ffi`, ffigen or jnigen,
`references/plugins-and-platform-views.md` for federated plugins and
platform views, `references/permissions-and-isolates.md` for runtime
permissions and background isolates, and
`references/testing-platform-code.md` for mocking channels and fake platform
interfaces.

For step-by-step setup (creating a plugin, running Pigeon or ffigen, adding a
platform view), defer to the docs.flutter.dev platform-integration guides
and, if your agent has them installed, the official `flutter/agent-plugins`
or `dart-lang/skills` recipes. This skill adds the architecture placement,
the secure defaults and the review checks.

### 3. Write with the checklist below, then run the checker

Read the code behind every hit before calling it `confirmed`.
`references/rules.md` lists each rule's detection and its known false
positives. Suppress a deliberate case in the code, with a reason:
`// plat-ignore: PLAT-006 the native registry owns this string` (on the
reported line or the line above) or `// plat-ignore-file: PLAT-004 <reason>`.

## WRITE checklist

**Channels and Pigeon**
1. One channel per native API, its name a `static const` in the one class
   that wraps it (PLAT-002), reverse-domain style (`com.example.app/battery`).
   Inject the channel instance so tests can replace it.
2. PREFER Pigeon once you have more than one or two methods or any structured
   data: `@HostApi` for Dart → native, `@FlutterApi` for native → Dart,
   `@async` on native methods that wait. Commit the schema in `pigeons/` and
   regenerate; never edit or review the generated files.
3. `invokeMethod<T>` returns `Future<T?>`. Check for `null`, validate ranges
   and enum values, and throw a typed exception at the source (PLAT-004).
4. Keep the `StreamSubscription` from `receiveBroadcastStream().listen` and
   cancel it in the owner's dispose hook (PLAT-005); prefer exposing the
   `Stream` from the source and letting logic own the subscription.
5. Clear `setMethodCallHandler`/`setMessageHandler` (set it to `null`) when
   the owner goes away, and register it once, not in `build()` or
   `didChangeDependencies()` (PLAT-008).

**Errors**
6. Catch `PlatformException` and `MissingPluginException` in the repository
   (or the source) and map them to the pattern's failure type (PLAT-003).
   Load `flutter-error-handling` for the mapping and how the UI shows it.
7. Branch on unsupported platforms in the source, with `kIsWeb` and
   `defaultTargetPlatform`, and return a typed "unsupported" result. Widgets
   never check the platform to decide whether a call will work.

**FFI**
8. Allocate inside `using((arena) { ... })`, or free in `finally`. Objects
   that hold native memory implement `Finalizable` and attach a
   `NativeFinalizer` (PLAT-006).
9. Run long synchronous native calls in `Isolate.run`, never in `build()` or
   a UI callback. Mark leaf calls `isLeaf: true` only when they are short and
   don't call back into Dart.
10. Load only bundled libraries by a constant name, or
    `DynamicLibrary.process()`; prefer native assets with build hooks
    (PLAT-007). Generate bindings with ffigen or jnigen rather than writing
    `lookupFunction` signatures by hand.

**Plugins, platform views, isolates, permissions**
11. Platform interfaces extend `PlatformInterface`, pass a private token, and
    call `PlatformInterface.verify(instance, _token)` in the `instance`
    setter. Implementations `extends` the interface; only test fakes
    `implements` it, with `MockPlatformInterfaceMixin` (PLAT-009).
12. Keep platform views out of scrolling lists and animations where you can;
    prefer texture-layer hybrid composition on Android when supported, and
    measure in profile mode (`flutter-performance`).
13. In a background isolate, pass `RootIsolateToken.instance!` in and call
    `BackgroundIsolateBinaryMessenger.ensureInitialized(token)` before any
    channel or plugin call (PLAT-010).
14. Request a permission when the user starts the feature that needs it,
    after a short rationale, never at startup (PLAT-011). Handle `denied`,
    `permanentlyDenied` and `restricted`, and offer `openAppSettings()`
    (PLAT-012). A service wraps `permission_handler`; the view triggers the
    request.

**Secure by default**
15. Validate every value from native at the source boundary; treat it like a
    server response.
16. Send the minimum over a channel. No tokens, passwords or full user
    records unless the native side needs them, and never log channel
    payloads (`flutter-secure-defaults`, SEC-004).
17. Free every native allocation, and never build a library path from a
    writable directory, an environment variable or user input.
18. Ask for the narrowest permission that works, and declare the matching
    iOS usage strings (`flutter-release`, REL-009).

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

## Related skills

These assume the suite is installed as sibling folders. If your agent doesn't
auto-load skills, read the path given. If a sibling is missing, carry on and
say which check you skipped.

- **`flutter-error-handling`** for mapping `PlatformException` and
  `MissingPluginException` to failures and showing them (ERR-*). Fallback:
  `../flutter-error-handling/SKILL.md` and
  `../flutter-error-handling/references/error-flow-by-architecture.md`.
- **`flutter-secure-defaults`** for the permission policy, secrets and what
  may be logged (SEC-*). Fallback: `../flutter-secure-defaults/SKILL.md` and
  `../flutter-secure-defaults/references/storage-and-privacy.md`.
- **`flutter-release`** for iOS usage descriptions, manifests and signing
  (REL-009). Fallback: `../flutter-release/SKILL.md`.
- **`flutter-performance`** for platform-view cost, isolates and jank
  diagnosis. Fallback: `../flutter-performance/SKILL.md` and
  `../flutter-performance/references/isolates.md`.
- **`flutter-testing`** for which layer to test first and fakes versus mocks.
  Fallback: `../flutter-testing/SKILL.md`.
- **`flutter-architecture`** for detecting the pattern and the layer rules.
  Fallback: `../flutter-architecture/SKILL.md`.
- **`flutter-feature-scaffold`** to generate a feature's source, repository
  and logic files in the project's pattern.
- **`dart-flutter-review`** merges PLAT findings into its report.

## References

| File | Read it when |
|---|---|
| `references/channels-and-pigeon.md` | writing a MethodChannel, EventChannel or BasicMessageChannel wrapper, choosing a codec, designing a Pigeon schema, handling errors and unsupported platforms |
| `references/ffi.md` | calling C, Objective-C, Swift or Java/Kotlin through `dart:ffi`, ffigen, jnigen or native assets; memory ownership; moving calls off the UI isolate |
| `references/plugins-and-platform-views.md` | writing or reviewing a federated plugin, a platform interface, an endorsed implementation, or a platform view |
| `references/permissions-and-isolates.md` | requesting runtime permissions, handling denials, and using channels from background isolates |
| `references/placement-by-architecture.md` | deciding where the channel, the mapping, the stream lifetime and the permission flow go in MVN, MVVM, Bloc/Cubit, Clean, Provider, GetX or Riverpod |
| `references/testing-platform-code.md` | mocking a channel with `TestDefaultBinaryMessengerBinding`, faking a platform interface, testing Pigeon APIs and logic over fake sources |
| `references/rules.md` | every PLAT rule: detection, why, fix, false positives; the reading-level slugs; what's checked elsewhere; calibration |
