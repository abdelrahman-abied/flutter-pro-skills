# Input, platform idioms, desktop and web

How a screen adapts to the input (touch, mouse, keyboard, trackpad) and the
platform's conventions, and what desktop windows and the web need. For
step-by-step guides, read docs.flutter.dev ("Adaptive and responsive
design", "Desktop support", "Web support") and the official
`flutter/agent-plugins` or `dart-lang/skills` recipes, if your agent has
them installed.

## Contents

1. Detect the platform the right way
2. Platform idioms and `.adaptive` widgets
3. Hover
4. Focus and keyboard shortcuts
5. Scrolling with a mouse and trackpad
6. Context menus
7. Text selection
8. Desktop windows
9. The web

## 1. Detect the platform the right way

| Need | Use | Why |
|---|---|---|
| look and feel (icons, page transitions, scroll physics, dialog style) | `Theme.of(context).platform` | follows `ThemeData.platform`, so a test, a preview or a user setting can switch it |
| the same outside a widget | `defaultTargetPlatform` | web-safe; follows `debugDefaultTargetPlatformOverride` in tests |
| "am I running in a browser" | `kIsWeb` | the only web check; compile-time constant |
| "does this device support X" (biometrics, NFC, badges) | a data source that checks `kIsWeb` first, then `defaultTargetPlatform` or the plugin | the widget asks the source; tests replace the source |
| OS version, executable path, environment | `dart:io` `Platform`, **only** in a source behind `kIsWeb`, or in a file picked by `if (dart.library.io)` | it throws on the web |

DON'T read `dart:io` `Platform` in widgets or logic (ADAPT-001 on the web,
ADAPT-002 elsewhere). `Platform.isIOS` is "the host is iOS", which tests
can't change, and on the web every `Platform` getter throws
`UnsupportedError`.

```dart
// guard order matters: kIsWeb first
final desktop = !kIsWeb && (Platform.isMacOS || Platform.isWindows || Platform.isLinux);   // safe
final broken = (Platform.isMacOS || Platform.isWindows) && !kIsWeb;                         // throws on web

// in a widget: no dart:io at all
final isApple = switch (Theme.of(context).platform) {
  TargetPlatform.iOS || TargetPlatform.macOS => true,
  _ => false,
};
```

On the web, `defaultTargetPlatform` reports the browser's OS (Android on
Chrome for Android, macOS on Safari for Mac). That is what you want for
idioms, and it's why it can't answer "am I on the web" (use `kIsWeb`).

## 2. Platform idioms and `.adaptive` widgets

- PREFER the adaptive constructors where both platforms have a native look:
  `Switch.adaptive`, `Slider.adaptive`, `Checkbox.adaptive`, `Radio.adaptive`,
  `CircularProgressIndicator.adaptive`, `RefreshIndicator.adaptive`,
  `AlertDialog.adaptive` with `showAdaptiveDialog`, `Icons.adaptive.*`
  (`Icons.adaptive.share`, `Icons.adaptive.arrow_back`).
- `ThemeData.platform` drives page transitions, scroll physics (bouncing on
  iOS/macOS) and typography; let it, rather than hard-coding per widget.
- A full Cupertino branch (`CupertinoApp`, `CupertinoPageScaffold`) is a
  product decision; when an app does it, the branch reads
  `Theme.of(context).platform` once near the root, not in every widget.
- Follow the platform's conventions where users will notice: back-swipe on
  iOS (keep `CupertinoPageTransitionsBuilder`), the system menu bar on
  macOS (`PlatformMenuBar`), Ctrl vs Cmd for shortcuts.

## 3. Hover

- Hover is an enhancement, never the only way to reach something
  (ADAPT-008). Touch has no hover, and keyboard users never trigger
  `onEnter`.
- `FocusableActionDetector` combines hover highlight, focus highlight,
  shortcuts and actions for a custom control. Material buttons and
  `InkWell` already show hover and focus states.
- `MouseRegion(cursor: SystemMouseCursors.click)` for custom tappables on
  desktop and web.
- Tooltips appear on hover and long press; they don't replace a label
  (`flutter-accessibility`).

```dart
FocusableActionDetector(
  onShowHoverHighlight: (v) => setState(() => _hovered = v),
  onShowFocusHighlight: (v) => setState(() => _focused = v),
  child: Row(children: [
    Expanded(child: Text(title)),
    if (_touch || _hovered || _focused) IconButton(icon: const Icon(Icons.delete), tooltip: 'Delete', onPressed: onDelete),
  ]),
)
// _touch: Theme.of(context).platform is android or iOS, or the last pointer was a touch
```

## 4. Focus and keyboard shortcuts

- Every interactive element must be reachable with Tab and activatable with
  Enter/Space. Focusability and focus order are `flutter-accessibility`'s
  (A11Y-no-keyboard-access, A11Y-focus-order).
- Desktop and web users expect shortcuts for the primary actions
  (ADAPT-no-shortcuts). `CallbackShortcuts` for a few keys; `Shortcuts` +
  `Actions` with `Intent`s when the same action has a button, a menu item
  and a shortcut.

```dart
final cmd = defaultTargetPlatform == TargetPlatform.macOS;
return Shortcuts(
  shortcuts: {
    SingleActivator(LogicalKeyboardKey.keyF, meta: cmd, control: !cmd): const SearchIntent(),
    SingleActivator(LogicalKeyboardKey.keyN, meta: cmd, control: !cmd): const NewItemIntent(),
  },
  child: Actions(
    actions: {
      SearchIntent: CallbackAction<SearchIntent>(onInvoke: (_) => _searchFocus.requestFocus()),
      NewItemIntent: CallbackAction<NewItemIntent>(onInvoke: (_) => onNew()),
    },
    child: Focus(autofocus: true, child: page),
  ),
);
```

- Show the shortcut in menus (`MenuItemButton(shortcut: …)`) so it's
  discoverable.
- Shortcuts call the same view callbacks the buttons call; the logic layer
  doesn't know about keys.

## 5. Scrolling with a mouse and trackpad

- Desktop and web users expect a visible scrollbar on long content. Material
  shows one on desktop by default for primary scroll views; for nested or
  horizontal lists, wrap them in `Scrollbar` with the same
  `ScrollController`.
- By default, mouse *drag* doesn't scroll (only the wheel does). Horizontal
  carousels then can't be scrolled with a mouse (ADAPT-no-desktop-scrolling):

```dart
ScrollConfiguration(
  behavior: ScrollConfiguration.of(context).copyWith(
    dragDevices: {PointerDeviceKind.touch, PointerDeviceKind.mouse, PointerDeviceKind.trackpad},
  ),
  child: ListView(scrollDirection: Axis.horizontal, children: cards),
)
```

- Arrow buttons on horizontal carousels help mouse users without a
  horizontal wheel.
- Keep scroll physics from the platform (`ThemeData.platform`), not
  hard-coded `BouncingScrollPhysics`.

## 6. Context menus

- Desktop and web users right-click; touch users long-press
  (ADAPT-no-context-menu). Offer the same actions both ways.

```dart
GestureDetector(
  onSecondaryTapUp: (d) => _menu.open(position: d.localPosition),
  onLongPress: () => _menu.open(),
  child: MenuAnchor(controller: _menu, menuChildren: actions, child: tile),
)
```

- Text fields and `SelectionArea` show the platform's text context menu
  (`contextMenuBuilder`); on the web, `BrowserContextMenu.disableContextMenu()`
  is needed before a Flutter menu can replace the browser's.

## 7. Text selection

- On web and desktop, users expect to select and copy readable text
  (ADAPT-text-not-selectable). Wrap content areas in `SelectionArea`; use
  `SelectionContainer.disabled` for parts that shouldn't be selectable
  (buttons, labels).
- `SelectableText` is for a single block; `SelectionArea` selects across
  widgets.
- Don't make interactive lists selectable; selection fights with taps.

## 8. Desktop windows

- Set a minimum window size (ADAPT-009), at least the compact width your
  layouts support:

```dart
Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  if (!kIsWeb && (Platform.isMacOS || Platform.isWindows || Platform.isLinux)) {   // composition root
    await windowManager.ensureInitialized();
    await windowManager.waitUntilReadyToShow(
      const WindowOptions(minimumSize: Size(400, 600), size: Size(1200, 800), center: true),
      () async => windowManager.show(),
    );
  }
  runApp(const App());
}
```

- Without a package, set it in the runner: `minSize`/`contentMinSize` in
  `macos/Runner/MainFlutterWindow.swift`, `WM_GETMINMAXINFO` in
  `windows/runner/win32_window.cpp`, `gtk_widget_set_size_request` in
  `linux/runner/my_application.cc`.
- Persisting the window's size and position is fine in a service; it is not
  layout state, and ADAPT-007 doesn't report a `windowSize` used for that.
- Desktop windows start at any size, including compact; desktop is not a
  size class.

## 9. The web

- `kIsWeb` is the web check. Keep it in sources and the composition root
  (ADAPT-kisweb-scattered); widgets ask a source.
- Code that needs `dart:io` on native and something else on the web goes in
  two files behind a conditional import:

```dart
// host_info.dart
export 'host_info_stub.dart' if (dart.library.io) 'host_info_io.dart';
```

- The URL strategy (`usePathUrlStrategy()`), deep links and browser
  back/forward are `flutter-navigation`'s.
- Browsers are resized constantly; everything in
  `size-classes-and-layout.md` applies with no extra API.
- Text selection, right-click and keyboard focus matter more on the web
  than anywhere else (sections 4, 6 and 7).
