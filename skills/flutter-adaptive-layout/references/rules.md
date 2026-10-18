# ADAPT rules: what the checker reports, and why

`scripts/check_adaptive.py` is static and read-only. It needs only the Python
standard library and no `pub get`. Every hit is a candidate: read the code
before you call a finding `confirmed`. Each rule lists the false positives it
knows about and how to suppress a deliberate case.

The checker judges what the other checkers can't see: whether platform
checks survive the web, whether the layout follows the space or the device,
whether breakpoints are shared, whether logic knows the screen, whether
mouse-only affordances have another path, whether desktop windows are
bounded and whether layout tests reset the view. Where a concern already has
an owner in the suite, ADAPT cross-references it instead of reporting it
again (section 4).

## Contents

1. How the checker reads the project
2. ADAPT-001 … ADAPT-010
3. Reading-level findings (ADAPT-<slug>)
4. Not checked here (cross-references)
5. Calibration

## 1. How the checker reads the project

- **Scope.** Every `.dart` file under `lib/` that `arch_check` lists in
  `files[]`, minus barrels, `di` files and generated files (`*.g.dart`,
  `*.freezed.dart`, files with a generated banner). ADAPT-010 also reads
  `test/**/*_test.dart` and `integration_test/**/*_test.dart`.
- **Targets.** The folders `android/`, `ios/`, `web/`, `macos/`, `windows/`
  and `linux/` at the project root say where the app runs. `web/` turns
  `dart:io` `Platform` reads from a style issue (ADAPT-002) into a crash
  (ADAPT-001). A package without platform folders is treated as running
  anywhere except the web.
- **Layers and roles** come from `../flutter-architecture/scripts/arch_check.py
  --json` (`files[]`). It reuses `$FPS_ARCH_JSON` when `dart-flutter-review`
  already ran it. Without the sibling skill, a path-based fallback is used
  and the `classification:` line says so.
- **Class kind.** A site inside a `State` or widget class is UI. Inside a
  `ChangeNotifier`, `Cubit`/`Bloc`, `GetxController`, a Riverpod notifier
  (`Notifier`, `AsyncNotifier`, `StateNotifier`, codegen `extends _$X`) or a
  `*ViewModel`, it is logic. `with _$X` (a freezed data class) is not logic.
- **Web guards.** `kIsWeb`, `kIsWasm`, and any project getter or constant
  whose body checks `kIsWeb` (`static bool get isDesktop => !kIsWeb && …`)
  count as guards. A guard counts when it is in the same expression
  (`kIsWeb || !Platform.isX`, `kIsWeb ? … : Platform.x`), in an enclosing
  `if (…)` (including collection `if (!kIsWeb) ...[`), in an early
  `if (kIsWeb) return`, or at every call site of the enclosing helper in
  the same file.
- **Breakpoint tokens.** A class or enum named like `Breakpoints`,
  `WindowSizeClass`, `ScreenSize`, `ScreenType` or `FormFactor`, or a
  constant named `*Breakpoint`, `*Threshold`, `*Width` with a size word
  (`mediumWidthBreakpoint`, `kTabletWidth`) and a value between 300 and 2000.
  Files that define tokens are never ADAPT-004. A dependency on
  `flutter_adaptive_scaffold`, `responsive_framework`, `responsive_builder`
  or `adaptive_breakpoints` also counts.
- **Placement notes.** Each finding's `note` carries the fix for the
  detected profile (`MVN: …`, `MVVM: …`, `Bloc: …`, `Riverpod: …`,
  `Provider: …`, `GetX: …`, plus `Clean: …` when the project has domain and
  data layers): where the size classes live, where a capability check goes,
  and what the logic layer exposes instead of the screen size. `--profile`
  overrides the detected pattern.
- **Suppression.** `// adapt-ignore: ADAPT-00x <reason>` on the reported
  line or the line above, or `// adapt-ignore-file: ADAPT-00x <reason>`
  anywhere in the file. Several IDs can be listed with commas. The reason is
  kept in `suppressed[]`.

## 2. Rules

### ADAPT-001 io-platform-on-web

**High** · all profiles · **only when the project has `web/`**

**Detects:** `Platform.isAndroid`/`isIOS`/`isMacOS`/`isWindows`/`isLinux`/
`isFuchsia`, `Platform.operatingSystem(Version)`, `localeName`,
`environment`, `resolvedExecutable` and the other `dart:io` `Platform`
getters, in a widget or `State` class, a logic class, top-level code of a
view or widget file, or the app root (`main.dart`, `bootstrap.dart`,
`app.dart`, layer `app`), with no web guard (section 1). `Platform` must come
from `dart:io` (with or without a prefix); `universal_io` and
`package:platform` are web-safe and ignored. Reported once per class, with
the number of uses in the note.

**Why:** on the web every `Platform` getter throws `UnsupportedError`. A
widget that reads it fails to build there; a notifier that reads it in
`build()` turns into an error state; the app root crashes at start-up.

```dart
// BAD: web/ exists
final back = Platform.isIOS ? Icons.arrow_back_ios : Icons.arrow_back;

// GOOD: look and feel from the theme (web-safe, overridable in tests)
final back = Theme.of(context).platform == TargetPlatform.iOS ? Icons.arrow_back_ios : Icons.arrow_back;

// GOOD: a capability check in a source, kIsWeb first
bool get supportsBadges => !kIsWeb && (Platform.isIOS || Platform.isMacOS);
```

**Profile notes:** the capability check moves into a data source (MVN,
Clean), a service (MVVM, Provider), a data provider (Bloc), a `GetxService`
(GetX) or a source provider (Riverpod), and the view reads a typed
"supported/unsupported" result.
**Not reported:** files picked by an `if (dart.library.io)` conditional
import or export; platform-specific paths (a directory named `android`,
`ios`, `macos`, `windows`, `linux`, `desktop`, `mobile`, `native`, `io`,
`window`, `tray` or `system_tray`, or a file name with one of those words,
such as `core_interface_desktop.dart`); data, domain and other non-UI files.
**False positives:** code that only runs after a guard in another file (a
desktop-only screen reached through a guarded route). Suppress with the
reason, or move the check behind the guard.

### ADAPT-002 platform-check-in-widget

**Low** · all profiles

**Detects:** a `dart:io` `Platform` getter in a widget or `State` class (or
top-level code of a view or widget file) that ADAPT-001 doesn't report:
the app has no `web/`, or the read is guarded. Reported once per class. This
automates the former reading slug `PLAT-platform-check-in-widget`.

**Why:** `Platform` reports the real host. `ThemeData.platform`,
`debugDefaultTargetPlatformOverride` and widget tests can't change it, so
the widget can't be previewed or tested as another platform, and the
branch often hides a capability question ("does this device have X") that
belongs in a source.

```dart
// BAD
if (!Platform.isMacOS) TextButton(onPressed: SystemNavigator.pop, child: const Text('Quit')),

// GOOD
if (Theme.of(context).platform != TargetPlatform.macOS) TextButton(...),
```

**False positives:** an OS *version* check (`Platform.operatingSystemVersion`)
that `defaultTargetPlatform` can't express. Move it into a source, or
suppress it with the reason.

### ADAPT-003 app-wide-orientation-lock

**Medium** (**Info** when the project has neither `android/` nor `ios/`) ·
all profiles

**Detects:** `SystemChrome.setPreferredOrientations([...])` whose list holds
only portrait or only landscape values, called at start-up: in `main()`,
`bootstrap()`, an `init*`/`setup*`/`configure*`/`*Initialization` function,
top-level code of the app root, or the `build`/`initState` of the class that
builds `MaterialApp`/`CupertinoApp`/`WidgetsApp`. Not when an enclosing
`if` or an earlier early return tests a size, the platform, the form factor
or the orientation.

**Why:** on Android 16, apps that target API 36 have their orientation,
resizability and aspect-ratio restrictions ignored on displays of 600 dp and
wider, iPadOS multitasking and
Android multi-window resize the app anyway, and foldables unfold into a
square. The landscape layout ships whether you built it or not.

```dart
// BAD
await SystemChrome.setPreferredOrientations([DeviceOrientation.portraitUp]);

// GOOD: lay out by width; if you must, lock only small phones
final view = WidgetsBinding.instance.platformDispatcher.views.first;
if (view.physicalSize.shortestSide / view.devicePixelRatio < 600) {
  await SystemChrome.setPreferredOrientations([DeviceOrientation.portraitUp]);
}
```

**Not reported:** a lock in one screen's `initState` (restore
`DeviceOrientation.values` in `dispose`), `DeviceOrientation.values`, a list
built from a variable.
**False positives:** a game or kiosk app that really is portrait-only on
every device. Suppress it with the reason, and test the large-screen
letterboxing.

### ADAPT-004 magic-breakpoint

**Low** · all profiles

**Detects:** `<`, `<=`, `>`, `>=` (and switch patterns such as
`case > 600`) between a width and a numeric literal from 300 to 2000. A
width is `constraints.maxWidth`/`minWidth`/`crossAxisExtent`,
`MediaQuery.sizeOf(context).width`, `MediaQuery.widthOf(context)`,
`MediaQuery.of(context).size.width`, `size.width`/`screenSize.width` and
`shortestSide`/`longestSide` of a screen size, `Get.width`, or a local
`width`/`screenWidth`/`maxWidth` assigned from one of those. Heights are
never reported.
- When the project has breakpoint tokens (section 1), every literal
  comparison outside the token files is reported, and the note names the
  tokens.
- Without tokens, comparisons are reported only when they repeat: two or
  more files, or two or more different values. A single literal in one place
  is a single breakpoint.

**Why:** literal breakpoints drift. One screen switches at 600, the next at
700, a third at 840, and the app jumps between layouts as the window
resizes.

```dart
// BAD
final columns = constraints.maxWidth > 600 ? 4 : 2;

// GOOD: lib/core/layout/window_size_class.dart (Material 3 widths)
enum WindowSizeClass {
  compact, medium, expanded, large, extraLarge;

  static WindowSizeClass fromWidth(double w) => w < 600 ? compact : w < 840 ? medium
      : w < 1200 ? expanded : w < 1600 ? large : extraLarge;
}
final columns = WindowSizeClass.fromWidth(constraints.maxWidth) == WindowSizeClass.compact ? 2 : 4;
```

**Profile notes:** where the size classes live (section 2 of the SKILL
table): `core/presentation/layout/` (MVN), `ui/core/` (MVVM), the `app_ui`
package or `app/view/` (Bloc), `core/` (Riverpod, Provider), `app/core/values/`
(GetX).
**Not reported:** the token files themselves; literals below 300 (a
component's own size, a board side); `widget.photo.width > 1000` and other
widths that aren't the window or the constraints.
**False positives:** a component's own minimum inside `LayoutBuilder` (a
toolbar that collapses its labels under 480 dp). Suppress it with
`adapt-ignore` and the reason, or name it as a component constant.

### ADAPT-005 device-identity-layout

**Medium** · all profiles

**Detects:**
- `isTablet`/`isPhone`/`isHandset`/`isIPad`/`isFoldable`/`deviceType`/
  `formFactor` assigned or returned from `Platform`, `defaultTargetPlatform`,
  `TargetPlatform`, `Theme.of(context).platform`, `GetPlatform`,
  `DeviceInfoPlugin` or a device model, with no size in the expression;
- a device model compared with `'iPad'`/`'tablet'`
  (`info.model.contains('iPad')`), `Device.get().isTablet`,
  `Device.screenType`.

**Why:** what the device *is* says nothing about the space the app has. An
iPad in Slide Over is 320 dp wide; a phone in landscape is wider than many
tablets in portrait; a desktop window is any size.

```dart
// BAD
final isTablet = defaultTargetPlatform == TargetPlatform.iOS && (await info.iosInfo).model.contains('iPad');

// GOOD
final sizeClass = WindowSizeClass.fromWidth(MediaQuery.sizeOf(context).width);
```

**Not reported:** expressions that also use a size, a width or a project
getter that measures one (`context.isNarrow`, any `context.<getter>`
extension), because the platform part then only picks an idiom.
**False positives:** analytics or support code that records the device
type and never touches layout. Suppress it with the reason.

### ADAPT-006 orientation-decides-layout

**Low** · all profiles

**Detects:** in a widget or `State`, `OrientationBuilder(...)`, or
`MediaQuery.orientationOf(context)` / `MediaQuery.of(context).orientation` /
`context.orientation` / `context.isLandscape` used in a comparison, a
ternary, a switch or a variable that is then compared or tested. Reported
once per class.

**Why:** orientation is the ratio of the window, not its size. A 1024 dp
tablet in portrait gets the phone layout; a phone in landscape gets the
tablet layout with 360 dp of height.

```dart
// BAD
final twoPane = MediaQuery.orientationOf(context) == Orientation.landscape;

// GOOD
final twoPane = WindowSizeClass.fromWidth(MediaQuery.sizeOf(context).width) != WindowSizeClass.compact;
```

**Not reported:** the orientation passed on without a decision (a camera
preview rotation, an ad size request).
**False positives:** media that really follows rotation (a full-screen video
or camera preview choosing its aspect). Suppress it with the reason.

### ADAPT-007 screen-size-in-logic

**Medium** · all profiles

**Detects:** a logic class (section 1) that reads `MediaQuery` size,
orientation or display features, `View.of`, `physicalSize`,
`platformDispatcher.views` or `Get.width`/`Get.size`, or declares a field or
parameter such as `screenWidth`, `screenSize`, `isTablet`, `isWideScreen`,
`useNavRail` or a field typed with the project's breakpoint token. Reported
once per class.

**Why:** the logic then changes when the window resizes, needs a view to be
tested, and couples state to one layout. The pattern's guarantee (logic is
UI-agnostic) is gone.

```dart
// BAD (MVN)
class InboxNotifier extends _$InboxNotifier {
  bool isTablet = false;
}

// GOOD: data only; the view picks one or two panes
class InboxNotifier extends _$InboxNotifier {
  void select(String id) => state = state.copyWith(selectedId: id);
}
```

**Profile notes:** MVN notifiers, MVVM view models, Bloc states, GetX
controllers and Riverpod providers expose data (`items`, `selectedId`). The
view reads `LayoutBuilder` or `MediaQuery.sizeOf`. A selection that must
survive a resize can be data in the logic layer; a layout flag can't.
**Not reported:** classes whose name says they are layout infrastructure
(`BreakpointNotifier`, `WindowSizeController`, `LayoutCubit`); freezed data
classes; `windowSize` used to persist a desktop window's bounds.
**False positives:** a logic class that computes a page size for a paged
API from the viewport. Pass the count in from the view instead, or suppress
it with the reason.

### ADAPT-008 hover-only-action

**Medium** · all profiles · not reported when the app targets only desktop

**Detects:** in a `State`, a `MouseRegion` whose `onEnter`/`onExit`/`onHover`
set a boolean field, that field is assigned nowhere else in the class
(no focus, tap or long-press path), and it gates an interactive widget:
`if (_hovered) IconButton(...)`, `_hovered ? IconButton(...) : null`, or
`Visibility(visible: _hovered, child: …onPressed…)`.

**Why:** touch screens have no hover, and keyboard users never trigger
`onEnter`. The action exists only for mouse users.

```dart
// BAD
MouseRegion(
  onEnter: (_) => setState(() => _hovered = true),
  onExit: (_) => setState(() => _hovered = false),
  child: Row(children: [title, if (_hovered) IconButton(icon: const Icon(Icons.delete), onPressed: onDelete)]),
)

// GOOD: always visible on touch; on desktop also on focus
FocusableActionDetector(
  onShowHoverHighlight: (v) => setState(() => _hovered = v),
  onShowFocusHighlight: (v) => setState(() => _focused = v),
  child: Row(children: [title, if (isTouch || _hovered || _focused) IconButton(...)]),
)
```

**Not reported:** hover that only changes a colour, a decoration or a
cursor; a flag also set from `onFocusChange`, `onLongPress` or a tap.
**False positives:** an action duplicated elsewhere on the screen (an
overflow menu). Suppress it with the reason.

### ADAPT-009 desktop-window-unbounded

**Low** · once per project

**Detects:** the project has `macos/`, `windows/` or `linux/`, shows desktop
intent (a desktop package such as `window_manager`, `desktop_window`,
`window_size`, `bitsdojo_window`, `menubar`, `macos_ui`, `fluent_ui`, or Dart
code that branches on `TargetPlatform.macOS/windows/linux`,
`Platform.isMacOS/isWindows/isLinux` or `isDesktop`), and no minimum window
size is set: no `setMinimumSize`, `minimumSize:` (`WindowOptions`),
`setMinWindowSize`, `setWindowMinSize`, `minWindowSize` in Dart, and no
`minSize`/`contentMinSize` (macOS runner), `WM_GETMINMAXINFO`/
`ptMinTrackSize` (Windows runner), `gtk_widget_set_size_request`/
`gtk_window_set_geometry_hints` (Linux runner). Reported at `runApp` in
`lib/main.dart`.

**Why:** users can drag a desktop window down to a few pixels, below the
smallest layout anyone built, and every screen overflows.

```dart
// GOOD (window_manager)
await windowManager.ensureInitialized();
await windowManager.setMinimumSize(const Size(360, 480));
```

**Not reported:** a `macos/` or `windows/` folder alone (generated by
`flutter create` and never shipped), with no desktop code or package.

### ADAPT-010 test-view-size-not-reset

**Low** · tests

**Detects:** in `*_test.dart`, `tester.view.physicalSize =`,
`tester.view.devicePixelRatio =`, the deprecated
`binding.window.physicalSizeTestValue =`/`devicePixelRatioTestValue =`, or
`setSurfaceSize(<size>)`, with no reset in the same test (or in the test
that calls the helper) and no reset in a `tearDown`: `reset()`,
`resetPhysicalSize()`, `resetDevicePixelRatio()`, `clear*TestValue()`,
`setSurfaceSize(null)`. Reported once per test or helper.

**Why:** flutter_test doesn't reset the test view between tests in a file.
The size leaks into the next test, which then passes or fails by order.

```dart
// GOOD
tester.view.physicalSize = const Size(1600, 2560);
tester.view.devicePixelRatio = 2;
addTearDown(tester.view.reset);
```

**Not reported:** helpers outside `*_test.dart` (shared test utilities);
helpers whose callers reset.

## 3. Reading-level findings (ADAPT-<slug>)

These need judgment the checker can't make. Report them with the same
format and a `likely` confidence unless you traced the code.

| ID | Severity | Look for | Fix |
|---|---|---|---|
| ADAPT-selection-lost-on-resize | Medium | the selected item, scroll position or form input disappears when the window crosses a breakpoint | keep `selectedId` outside the branch (view `State` or logic data), `PageStorageKey` on lists, `GlobalKey` only where a subtree must move |
| ADAPT-insets-ignored | Medium | content under the notch, status or navigation bar, or the keyboard; edge-to-edge (Android 15+) without `SafeArea`, `paddingOf`/`viewPaddingOf` or `viewInsetsOf` | `SafeArea` per screen body; `Scaffold(resizeToAvoidBottomInset:)` or `viewInsetsOf` for sheets |
| ADAPT-content-under-hinge | Medium | a two-pane layout on a foldable that puts content across the hinge | split at `MediaQuery.displayFeaturesOf(context)` bounds; keep tap targets off the fold |
| ADAPT-no-shortcuts | Medium | a desktop or web app whose primary actions (new, search, save, delete) have no keyboard shortcut | `Shortcuts` + `Actions` or `CallbackShortcuts`; show the shortcut in menus |
| ADAPT-mediaquery-for-component | Low | `MediaQuery.sizeOf` sizing a widget that sits in a pane, a dialog or a list item | `LayoutBuilder` gives the space the widget actually gets |
| ADAPT-nav-not-adaptive | Low | `NavigationBar` on every width, or a rail on phones | bar on compact, rail on medium, extended rail or drawer on expanded and up |
| ADAPT-unbounded-content-width | Low | paragraphs, forms or cards stretched across a 1600 dp window | `Center` + `ConstrainedBox(maxWidth: 600–840)` |
| ADAPT-fixed-screen-size | Low | `SizedBox(width: 375, height: 812)` or a `Container` sized for one phone around a screen | let the screen fill its constraints; size components, not screens |
| ADAPT-no-desktop-scrolling | Low | horizontal lists a mouse can't scroll; no scrollbars on desktop and web | `Scrollbar` with a controller; `ScrollConfiguration` adding `PointerDeviceKind.mouse` to `dragDevices` for carousels |
| ADAPT-no-context-menu | Low | desktop or web lists with no right-click (or long-press) menu where the platform expects one | `GestureDetector(onSecondaryTapUp:)` + `MenuAnchor`, or `contextMenuBuilder` on text fields |
| ADAPT-text-not-selectable | Low | readable content on web or desktop that can't be selected or copied | `SelectionArea` around the content |
| ADAPT-non-adaptive-control | Low | `Switch`, `Slider`, `CircularProgressIndicator`, `AlertDialog` not adaptive in an app that otherwise follows platform idioms | `Switch.adaptive`, `Slider.adaptive`, `CircularProgressIndicator.adaptive`, `showAdaptiveDialog` |
| ADAPT-kisweb-scattered | Low | `kIsWeb` branches spread across widgets | ask a source; read `kIsWeb` in sources and the composition root |
| ADAPT-no-size-class-tests | Low | adaptive screens tested only at the default 800×600 test size | one test (or golden) per size class, see `testing-adaptive-layouts.md` |

## 4. Not checked here (cross-references)

| Concern | Owner |
|---|---|
| `MediaQuery.of(context).size` instead of `sizeOf` | the `mediaquery-of` heuristic and `UI-*` (`flutter-ui-practices`). ADAPT-006 beats it only on a line that reads the orientation to choose a layout |
| Physical `left`/`right` geometry | I18N-012 |
| Magic spacing literals | DS-003 (ADAPT-004 judges only width comparisons) |
| Text scaling, fixed heights around text | A11Y-004 / A11Y-006 |
| Tap-target size | A11Y-005 |
| Focusability of custom controls, focus order | A11Y-no-keyboard-access / A11Y-focus-order |
| Eager lists and grids | PERF-001 |
| Navigation shells, routes, web URL strategy | NAV and `flutter-navigation` |
| `BuildContext` in logic | ARCH-102 (ADAPT-007 reports the size knowledge; on the same line ARCH-102 wins and ADAPT-007 is cited) |
| Platform channels in widgets | PLAT-001 (ADAPT-002 owns only the platform check, and replaces `PLAT-platform-check-in-widget`) |
| Store target SDK and manifests | REL |

## 5. Calibration

Run on the suite's shared calibration pool (suite contracts §24 and §34).
Each project with its own `pubspec.yaml` and `lib/` was run separately (163
projects, about 2,800 Dart files). Every high and medium hit was read and
judged by the pattern's canonical source; low hits were read too.

| App | Commit | Profile | Targets | Hits (per rule) | TP / FP |
|---|---|---|---|---|---|
| flutter/samples `compass_app` app + server (canonical) | flutter/samples@5541c59 | mvvm | all six | none | 0 / 0 |
| flutter/samples `material_3_demo` (canonical) | flutter/samples@5541c59 | setstate | all six | ADAPT-008 ×1 (medium), ADAPT-010 ×1 (low) | 2 / 0 |
| flutter/samples `desktop_photo_search` material + fluent_ui (canonical) | flutter/samples@5541c59 | provider | macos, windows, linux | ADAPT-002 ×2, ADAPT-009 ×2 (low) | 4 / 0 |
| flutter/samples `navigation_and_routing` (canonical) | flutter/samples@5541c59 | unknown (setState) | all six | none | 0 / 0 |
| flutter/samples, the other 30 projects incl. `platform_design`, `add_to_app/**`, `web_embedding` | flutter/samples@5541c59 | various | various | none | 0 / 0 |
| felangel/bloc `examples/*` + `packages/*`, 40 projects (canonical) | felangel/bloc@b9be1e2 | bloc | web, macos, ios | none | 0 / 0 |
| rrousselGit/riverpod `examples/*` + packages, 26 projects (canonical) | rrousselGit/riverpod@87aad84 | riverpod | macos only for two examples | none after the fix | 0 / 0 (2 low FPs before) |
| immich-app/immich `mobile` (+ `packages/ui`) | immich-app/immich@188d64e | riverpod | android, ios | ADAPT-002 ×9, ADAPT-004 ×8, ADAPT-006 ×3 (low) | 20 / 0 (1 medium FP before) |
| lichess-org/mobile | lichess-org/mobile@99e1fb7 | riverpod | android, ios, linux | ADAPT-002 ×3, ADAPT-004 ×4, ADAPT-006 ×2, ADAPT-009 ×1 (low) | 10 / 0 (1 medium FP before) |
| hiddify/hiddify-app | hiddify/hiddify-app@f26aadb | riverpod | all six | ADAPT-001 ×1 (high), ADAPT-002 ×1, ADAPT-004 ×1 (low) | 3 / 0 (1 high FP before) |
| gskinnerTeam/flutter-wonderous-app | gskinnerTeam/flutter-wonderous-app@747b945 | provider | web, macos, windows, android, ios | ADAPT-006 ×3 (low) | 3 / 0 |
| flutter/news_toolkit `flutter_news_example`, 30 projects | flutter/news_toolkit@6655bbc | bloc | android, ios | none | 0 / 0 |
| VGVentures/io_flip, 26 projects | VGVentures/io_flip@964e511 | bloc | web | ADAPT-004 ×4 (low) | 4 / 0 |

**The canonical apps have no high or medium false positives.** The one
medium on a canonical app is a true positive: `material_3_demo`'s colour
palette shows its copy button only while a `MouseRegion` hover flag is set,
so the action can't be reached on phones. Its lows are true positives too: a
test helper sets `devicePixelRatio` and `physicalSize` with no reset, and
`desktop_photo_search` branches a menu item on `Platform.isMacOS` in a
widget and never sets a minimum window size.

Non-canonical true positives include hiddify's connection notifier reading
`Platform.isIOS` in `build()` of an app that ships `web/` (the home
screen's button watches it), immich's eight `constraints.maxWidth > 600`
checks across five screens and its navigation choosing a rail by
orientation, lichess's grid breakpoints bypassing its own `FormFactor`
tokens, and io_flip's 400/500/900 literals across four views.
lichess's and wonderous's orientation locks are correctly silent: one is
guarded by the shortest side, the other is built from a variable.

**False-positive causes fixed, each with a `calib_<app>` regression fixture
and a test that the related true positive still fires:**

| Fixture | Cause | Fix |
|---|---|---|
| `calib_hiddify` | a static helper reading `Platform.resolvedExecutable` was called only behind `PlatformUtils.isWindows` (a getter that checks `kIsWeb`), so the ADAPT-001 high was unreachable on the web | getters and constants that check `kIsWeb` are learnt as guards, and a helper whose every call site in the file is guarded is guarded |
| `calib_immich` | `isIpad = defaultTargetPlatform == TargetPlatform.iOS && !context.isMobile` combined the platform with a width extension from another package (ADAPT-005 medium) | a `context.<getter>` or a project getter that measures the space marks the expression as size-based |
| `calib_lichess` | a freezed data class (`with _$BackgroundImage`) with a `viewportWidth` parameter was read as a Riverpod codegen notifier (ADAPT-007 medium) | only `extends _$X` is a codegen notifier; `with _$X` is data |
| `calib_riverpod_macos` | two riverpod examples ship only a generated `macos/` folder and were told to set a minimum window size (ADAPT-009 low) | desktop intent needs a desktop package or desktop-specific Dart code; `calib_samples_desktop` keeps the desktop-first true positive |

**Known limits.** ADAPT-001 doesn't follow guards across files: a widget
built only from a route that a `kIsWeb` redirect hides is still reported.
ADAPT-004 recognises widths by their source (constraints, `MediaQuery`,
names like `screenWidth`); a width passed through several variables or a
custom extension is missed. ADAPT-008 follows one boolean field per
`MouseRegion`, not hover state kept in a `ValueNotifier` or a parent.
ADAPT-009 doesn't parse window sizes set by native code it doesn't
recognise.
