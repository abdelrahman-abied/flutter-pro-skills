# Size classes and layout

How to make a screen follow the space it gets: one set of breakpoints, the
right measurement, navigation and panes by size class, foldables,
orientation, and insets. For step-by-step guides, read docs.flutter.dev's
"Adaptive and responsive design" and "Large screen devices" pages (and the
official `flutter/agent-plugins` or `dart-lang/skills` recipes, if your agent
has them installed).

## Contents

1. Responsive vs adaptive
2. Window size classes, defined once
3. LayoutBuilder or MediaQuery.sizeOf
4. Navigation bar, rail or drawer
5. List-detail and two panes
6. Foldables
7. Orientation and multi-window
8. Safe areas, insets and edge-to-edge
9. Content width on large windows

## 1. Responsive vs adaptive

- **Responsive:** the layout changes with the space. One column becomes
  two, a grid gains columns, a sheet becomes a side panel.
- **Adaptive:** the behaviour changes with the platform and the input. A
  rail instead of a bar, hover and focus states, keyboard shortcuts,
  scrollbars, right-click menus, Cupertino-style switches on iOS.

Most screens need both. Decide the *structure* from the space and the
*interaction* from the input and platform, and never the other way round:
a 1024 dp iPad wants the expanded layout and touch interaction; a 500 dp
desktop window wants the compact layout and mouse interaction.

## 2. Window size classes, defined once

Material 3 classifies the window width (logical pixels, dp):

| Size class | Width | Typical devices | Navigation | Panes |
|---|---|---|---|---|
| compact | < 600 | phones in portrait | `NavigationBar` | one |
| medium | 600–839 | tablets in portrait, foldables unfolded | `NavigationRail` | one, or list-detail with a narrow list |
| expanded | 840–1199 | tablets in landscape, small desktop windows | rail or `NavigationDrawer` | two |
| large | 1200–1599 | desktops | extended rail or drawer | two, wider |
| extra-large | ≥ 1600 | large desktop windows | drawer | two or three |

These are Material's guidance (m3.material.io, "Window size classes").
A project may pick other numbers; what matters is that every screen uses
the same ones (ADAPT-004). DO define them once:

```dart
// lib/core/layout/window_size_class.dart (or the design-system package)
enum WindowSizeClass {
  compact, medium, expanded, large, extraLarge;

  static WindowSizeClass fromWidth(double width) {
    if (width < 600) return compact;
    if (width < 840) return medium;
    if (width < 1200) return expanded;
    if (width < 1600) return large;
    return extraLarge;
  }

  static WindowSizeClass of(BuildContext context) => fromWidth(MediaQuery.sizeOf(context).width);

  bool get isCompact => this == compact;
  bool operator >=(WindowSizeClass other) => index >= other.index;
}
```

If the project already has a design system, the size classes sit next to its
spacing and type tokens (`flutter-design-system`). If it uses
`flutter_adaptive_scaffold` or `responsive_framework`, use their breakpoints
instead of adding a second set.

AVOID deriving a size class from the device (`isTablet` from the model or
the platform, ADAPT-005) or from the orientation (ADAPT-006). Use the
shortest side only for decisions that really follow the device's physical
size, such as locking orientation on small phones.

## 3. LayoutBuilder or MediaQuery.sizeOf

| Question | Use |
|---|---|
| How much space does *this widget* get? (a card in a grid, a pane, a dialog body, a list item) | `LayoutBuilder` → `constraints.maxWidth` |
| How big is the *window*? (page structure, navigation, which route shows the detail) | `MediaQuery.sizeOf(context)` |
| Notch, status bar, keyboard | `MediaQuery.paddingOf`, `viewPaddingOf`, `viewInsetsOf` |
| Hinge or fold | `MediaQuery.displayFeaturesOf` |

Reasons:
- A widget inside a 400 dp pane of a 1400 dp window must lay out for 400.
  `MediaQuery` says 1400 (ADAPT-mediaquery-for-component).
- `MediaQuery.sizeOf(context)` rebuilds only when the size changes;
  `MediaQuery.of(context).size` rebuilds on every MediaQuery change
  (keyboard, text scale, padding). The `mediaquery-of` heuristic and
  `flutter-ui-practices` report the latter.
- `LayoutBuilder` rebuilds when its constraints change, which is what you
  want for a component. Don't put heavy work in its builder.

```dart
class ProductGrid extends StatelessWidget {
  const ProductGrid({super.key, required this.items});
  final List<Product> items;

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(
      builder: (context, constraints) {
        final columns = switch (WindowSizeClass.fromWidth(constraints.maxWidth)) {
          WindowSizeClass.compact => 2,
          WindowSizeClass.medium => 3,
          _ => 4,
        };
        return GridView.builder(
          gridDelegate: SliverGridDelegateWithFixedCrossAxisCount(crossAxisCount: columns),
          itemCount: items.length,
          itemBuilder: (context, i) => ProductCard(item: items[i]),
        );
      },
    );
  }
}
```

PREFER `SliverGridDelegateWithMaxCrossAxisExtent(maxCrossAxisExtent: 240)`
when the number of columns should simply follow the width: no breakpoint
needed at all. Grid and list cost on large screens is `flutter-performance`'s.

## 4. Navigation bar, rail or drawer

The shell route (`StatefulShellRoute.indexedStack`, one branch per tab,
`goBranch`) belongs to `flutter-navigation`. This skill picks the widget
the shell shows:

```dart
class AppShell extends StatelessWidget {
  const AppShell({super.key, required this.shell});
  final StatefulNavigationShell shell;

  static const _destinations = [
    (icon: Icons.inbox_outlined, selected: Icons.inbox, label: 'Inbox'),
    (icon: Icons.search, selected: Icons.search, label: 'Search'),
    (icon: Icons.person_outline, selected: Icons.person, label: 'Profile'),
  ];

  @override
  Widget build(BuildContext context) {
    final size = WindowSizeClass.of(context);
    void select(int i) => shell.goBranch(i, initialLocation: i == shell.currentIndex);
    if (size.isCompact) {
      return Scaffold(
        body: shell,
        bottomNavigationBar: NavigationBar(
          selectedIndex: shell.currentIndex,
          onDestinationSelected: select,
          destinations: [
            for (final d in _destinations)
              NavigationDestination(icon: Icon(d.icon), selectedIcon: Icon(d.selected), label: d.label),
          ],
        ),
      );
    }
    return Scaffold(
      body: Row(
        children: [
          NavigationRail(
            extended: size >= WindowSizeClass.large,
            selectedIndex: shell.currentIndex,
            onDestinationSelected: select,
            labelType: size >= WindowSizeClass.large ? NavigationRailLabelType.none : NavigationRailLabelType.all,
            destinations: [
              for (final d in _destinations)
                NavigationRailDestination(icon: Icon(d.icon), selectedIcon: Icon(d.selected), label: Text(d.label)),
            ],
          ),
          const VerticalDivider(width: 1),
          Expanded(child: shell),
        ],
      ),
    );
  }
}
```

- Keep the destinations in one list that both widgets read, so the bar and
  the rail never disagree.
- The branch state (`indexedStack`) survives the switch because the shell,
  not the bar, owns it.
- `flutter_adaptive_scaffold` (`AdaptiveScaffold`) packages the same idea
  with animations; it brings its own breakpoints, so use them as the
  project's tokens.

## 5. List-detail and two panes

The bug to avoid: the user selects an item on a tablet, rotates or resizes
the window, and the selection is gone (ADAPT-selection-lost-on-resize).
The fix is to keep the selection *outside* the layout branch.

```dart
class InboxPage extends StatefulWidget {
  const InboxPage({super.key});
  @override
  State<InboxPage> createState() => _InboxPageState();
}

class _InboxPageState extends State<InboxPage> {
  String? _selectedId;                      // survives the compact <-> expanded switch

  @override
  Widget build(BuildContext context) {
    final twoPane = WindowSizeClass.of(context) >= WindowSizeClass.expanded;
    final list = MessageList(
      key: const PageStorageKey('inbox-list'),  // keeps the scroll offset across layouts
      selectedId: twoPane ? _selectedId : null,
      onSelect: (id) {
        setState(() => _selectedId = id);
        if (!twoPane) context.push('/inbox/$id');  // compact: the detail is its own route
      },
    );
    if (!twoPane) return list;
    return Row(
      children: [
        SizedBox(width: 360, child: list),
        const VerticalDivider(width: 1),
        Expanded(child: _selectedId == null ? const EmptyDetail() : MessageDetail(id: _selectedId!)),
      ],
    );
  }
}
```

- The detail is addressable (`/inbox/:id`) so compact layouts, deep links
  and the web URL all work; the route definition is `flutter-navigation`'s.
- When the window widens while a detail route is open on top, pop it and
  show the same id in the right pane (listen to the size class change in the
  detail screen, or let the router redirect on expanded).
- Where the selection lives depends on the pattern
  (`placement-by-architecture.md`): view `State` is enough for most apps;
  put `selectedId` in the logic layer as *data* when other screens need it.
  Never store "two-pane mode" in logic (ADAPT-007).

## 6. Foldables

- `MediaQuery.displayFeaturesOf(context)` lists hinges, folds and cutouts
  with their `bounds` and `state` (`DisplayFeatureState.postureFlat`,
  `postureHalfOpened`).
- A vertical hinge splits the window in two; keep panes on either side and
  keep tap targets off the fold (ADAPT-content-under-hinge).
- `DisplayFeatureSubScreen` (Material) positions dialogs and sheets on one
  side of the hinge; Material dialogs already use it.

```dart
final hinge = MediaQuery.displayFeaturesOf(context)
    .where((f) => f.type == DisplayFeatureType.hinge || f.type == DisplayFeatureType.fold)
    .firstOrNull;
if (hinge != null && hinge.bounds.height > hinge.bounds.width) {
  // vertical hinge: left pane ends at hinge.bounds.left, right pane starts at hinge.bounds.right
}
```

## 7. Orientation and multi-window

- AVOID app-wide orientation locks (ADAPT-003). On Android 16, apps that
  target API 36 have orientation, resizability and aspect-ratio
  restrictions ignored on displays of 600 dp and wider. iPadOS
  multitasking and Android multi-window resize the app anyway, and a
  foldable changes from a phone to a near-square tablet when it unfolds.
- If one screen needs a fixed orientation (a camera, a board game), set it
  in that screen and restore it:

```dart
@override
void initState() {
  super.initState();
  SystemChrome.setPreferredOrientations([DeviceOrientation.portraitUp]);
}

@override
void dispose() {
  SystemChrome.setPreferredOrientations(DeviceOrientation.values);
  super.dispose();
}
```

- If the product really is phone-portrait only, lock only small windows (the
  shortest side under 600 dp) and test the large-screen letterbox.
- Don't use orientation to pick a layout (ADAPT-006); a split-screen window
  on a landscape tablet is "portrait".
- Multi-window means the window resizes at any time. Everything above
  (size classes, `LayoutBuilder`, selection outside the branch) is what
  makes that safe; there is no separate API to handle.

## 8. Safe areas, insets and edge-to-edge

- Android 15+ (target API 35) draws edge-to-edge by default; content runs
  under the status and navigation bars unless you pad it. iOS has the notch
  and the home indicator.
- `SafeArea` around each screen's body, or read
  `MediaQuery.paddingOf(context)` (insets after system UI) and
  `viewPaddingOf` (insets including what the keyboard covers).
- `MediaQuery.viewInsetsOf(context).bottom` is the keyboard height. A
  `Scaffold` resizes for it by default (`resizeToAvoidBottomInset`); bottom
  sheets and custom overlays must add it themselves.
- `Scaffold` + `AppBar` already handle the top inset; don't double-pad.
- Landscape phones have the notch on a side: use `SafeArea(left: true,
  right: true)` (the default) rather than only the top.

## 9. Content width on large windows

- A paragraph stretched to 1600 dp is unreadable, and a form field that
  wide looks broken (ADAPT-unbounded-content-width).

```dart
Center(
  child: ConstrainedBox(
    constraints: const BoxConstraints(maxWidth: 720),
    child: form,
  ),
)
```

- Use the extra space for structure (a second pane, a side panel, more grid
  columns), not for longer lines.
- AVOID fixed screen-sized boxes (`SizedBox(width: 375, height: 812)`,
  ADAPT-fixed-screen-size). Size components; let screens fill their
  constraints.
