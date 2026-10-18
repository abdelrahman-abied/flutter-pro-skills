---
name: flutter-adaptive-layout
description: Write and review Flutter layouts that adapt to phones, tablets, foldables, desktop windows and the web, placed by the app's architecture. Covers size-class tokens defined once, LayoutBuilder vs MediaQuery.sizeOf, bar, rail or drawer by width, list-detail that survives a resize, foldables, no app-wide orientation lock, safe areas, hover, focus, shortcuts, mouse scrolling, context menus, SelectionArea, defaultTargetPlatform and .adaptive widgets (dart io Platform in UI throws on the web), desktop minimum window size, size-class tests. Ships an ADAPT checker. Use it when a screen must fit more than one size or platform, or someone says tablet, iPad, foldable, desktop, responsive or breakpoint. For shells and routes load flutter-navigation, for tokens flutter-design-system, for text scale flutter-accessibility, for list cost flutter-performance, for native code flutter-platform-integration.
license: MIT
metadata:
  author: abdelrahman-abied
  version: "1.7.1"
  suite: flutter-pro-skills
---

# Flutter adaptive layout

> **Writing a standard feature?** If you're filling in a feature that
> `flutter-feature-scaffold` generated, its cross-cutting rules already cover
> this skill's write-time defaults (one or two panes by width). You can stop reading here and check
> once at the end with `bash ../dart-flutter-review/scripts/review.sh <project-root> --diff HEAD --findings-only`.
> Read on when the work is about this area itself, or to fix a finding it reports.

One Flutter codebase runs on a 360 dp phone, a 1280 dp tablet, a foldable
with a hinge down the middle, a resizable desktop window and a browser tab.
Layouts written for one of them fail quietly on the others: a
`Platform.isIOS` in a widget throws on the web, a portrait lock is ignored on
Android 16+ tablets so the never-tested landscape layout ships anyway, two
screens switch to two panes at 600 and 700 dp, a delete button only appears
on mouse hover so touch users can't reach it, and a desktop window shrinks
until everything overflows. This skill writes layouts that follow the space
and the input they actually get, placed where the project's architecture
expects them.

The core split holds in every pattern:

- **Responsive** means the layout follows the available space. Choose by
  width, never by device type or orientation. Use `LayoutBuilder` for the
  space a widget actually gets, and `MediaQuery.sizeOf(context)` for the
  window.
- **Adaptive** means behaviour follows the platform and the input: a
  navigation bar, rail or drawer; hover and focus; keyboard shortcuts;
  scrollbars and mouse drag; context menus; text selection; platform look
  and feel through `Theme.of(context).platform`.
- **Breakpoints are tokens.** The window size classes are defined once, in
  the design system or `core/`, and every screen compares against them.
  Material 3 uses compact (< 600 dp), medium (600–839), expanded
  (840–1199), large (1200–1599) and extra-large (≥ 1600). A project may
  define its own; consistency matters more than the numbers.
- **Logic never knows the screen.** Notifiers, view models, blocs and
  controllers expose data. The view picks one pane or two, and keeps the
  selection somewhere that survives the switch.
- **Correct and secure by default:** `dart:io` `Platform` in code that also
  runs on the web is a crash, not a style issue. Don't derive layout from
  device identity (`isTablet` from the model name). Desktop windows have no
  minimum size unless the app sets one.

## Workflow

### 1. Detect the architecture and the platforms

Check your agent's project instructions file (`AGENTS.md`, `CLAUDE.md`,
`GEMINI.md`, `.cursor/rules/…`, `.github/copilot-instructions.md`) for a
declared pattern and any breakpoint conventions. A declared convention wins.
Then run the checker. It is read-only, uses only the Python standard
library, and doesn't need `pub get`:

```bash
python3 -I <skill-dir>/scripts/check_adaptive.py <project-root>                     # text report
python3 -I <skill-dir>/scripts/check_adaptive.py <project-root> --json              # schema flutter-pro-skills/adaptive-layout@1
python3 -I <skill-dir>/scripts/check_adaptive.py <project-root> --files changed.txt # diff review
python3 -I <skill-dir>/scripts/check_adaptive.py <project-root> --profile bloc      # declared pattern wins
```

The CLI is `check_adaptive.py <project-root> [--json] [--files
<list-file-or-comma-list>] [--profile auto|mvn|mvvm|bloc|mvc|getx|provider|riverpod|setstate]
[--max n]`. It exits `0` whenever a report is produced and `2` on a usage
error. It reads Dart under `lib/` (and widget tests for ADAPT-010),
`pubspec.yaml`, and which of `web/`, `macos/`, `windows/`, `linux/`,
`android/` and `ios/` exist, to know where the app runs. Roles and the
profile come from the `flutter-architecture` checker
(`../flutter-architecture/scripts/arch_check.py --json`, or `$FPS_ARCH_JSON`
when a review already ran it). If that sibling is missing, it falls back to
path-based detection and says so on the `classification:` line.

```text
== ADAPTIVE LAYOUT
  profile: mvn + clean (arch_check, confidence high)
  classification: arch_check files[]
  scanned: 96 files (4 generated skipped), 12 test files; platforms: android, ios, web; breakpoint tokens: none; ...
  [ADAPT-001] io-platform-on-web (high) x1 — dart:io Platform (Platform.isAndroid, ...) is read in a widget ...
      lib/features/feed/presentation/view/feed_view.dart:31  final back = Platform.isIOS ? ... : ...;   [FeedView (widget) reads Platform.isIOS, ...]
```

### 2. Place each piece by the pattern

| Piece | MVN | MVVM | Bloc / Cubit | Clean | Provider | GetX | Riverpod |
|---|---|---|---|---|---|---|---|
| size classes (tokens) | `core/presentation/layout/` or the design-system package | `ui/core/` | `app_ui` package or `app/view/` | presentation `core/` | `core/` or theme folder | `app/core/values/` | `core/` (plain enum, not a provider) |
| one pane or two | the view | the view | the view (`BlocBuilder`) | the view | the widget | `GetView` / `Obx` | the `ConsumerWidget` |
| selected item | view `State`, or `selectedId` as data in the notifier | view `State` or a view-model field | `selectedId` in the state | as MVN | view `State` | an `Rx` field | view `State` or a notifier field |
| "is this supported here" | data source + use case | service | data provider | data source | service | `GetxService` | source provider |
| shell (bar / rail) | `flutter-navigation` builds it; this skill picks the widget per size class | same | same | same | same | same | same |

Read `references/size-classes-and-layout.md` before writing a breakpoint, a
two-pane screen or a navigation scaffold, `references/input-and-platform.md`
for hover, focus, shortcuts, scrolling, menus, selection, platform idioms,
desktop windows and the web, `references/placement-by-architecture.md` for
the per-pattern layouts, and `references/testing-adaptive-layouts.md` for
size-class and platform tests.

For step-by-step guides, defer to docs.flutter.dev ("Adaptive and responsive
design", "Large screen devices", "SafeArea and MediaQuery") and, if your
agent has them installed, the official `flutter/agent-plugins` or
`dart-lang/skills` recipes. This skill adds the architecture placement, the
correctness defaults and the review checks.

### 3. Write with the checklist below, then run the checker

Read the code behind every hit before calling it `confirmed`.
`references/rules.md` lists each rule's detection and its known false
positives. Suppress a deliberate case in the code, with a reason:
`// adapt-ignore: ADAPT-004 this card's own minimum, not a window breakpoint`
(on the reported line or the line above) or
`// adapt-ignore-file: ADAPT-002 <reason>`.

## WRITE checklist

**Space and breakpoints**
1. DO define the size classes once, as an enum with a `fromWidth`
   constructor or a small constants class, and compare against it
   everywhere (ADAPT-004). If the design system already has breakpoint
   tokens, use those (`flutter-design-system`).
2. DO choose a component's layout from `LayoutBuilder` constraints (the
   space it gets inside a pane or a list) and a page's layout from
   `MediaQuery.sizeOf(context)` (the window). Prefer `sizeOf` and the other
   aspect methods over `MediaQuery.of(context)`, so the widget rebuilds only
   on the aspect it reads.
3. AVOID deciding layout by device type or orientation (ADAPT-005,
   ADAPT-006). A tablet in split view is phone-sized; a phone in landscape
   is wider than a tablet in portrait.
4. PREFER `ConstrainedBox(constraints: BoxConstraints(maxWidth: …))` for
   readable content on wide windows, instead of stretching text and forms to
   the full width.

**Navigation and panes**
5. DO switch the navigation widget by size class: `NavigationBar` when
   compact, `NavigationRail` when medium, an extended rail or a
   `NavigationDrawer` when expanded and up. Keep the destinations in one
   list both widgets read. The shell route itself belongs to
   `flutter-navigation` (`StatefulShellRoute.indexedStack`).
6. DO build list-detail so the selection survives the switch: keep
   `selectedId` outside the branch (view `State`, or data in the logic
   layer), give the list a `PageStorageKey`, and on compact push the detail
   route for the same id.
7. CONSIDER foldables: read `MediaQuery.displayFeaturesOf(context)` and
   keep panes off a hinge (`TwoDimensionalDisplayFeature` bounds), or use
   `TwoPane`-style splitting that respects it.

**Orientation, windows and insets**
8. AVOID app-wide orientation locks (ADAPT-003). Android 16 ignores them on
   screens 600 dp and wider once the app targets API 36, and multi-window
   resizes the app anyway. Lock one screen
   if you must, and restore `DeviceOrientation.values` on dispose.
9. DO wrap screen content in `SafeArea` (or read `MediaQuery.paddingOf` /
   `viewPaddingOf`) and respect `viewInsetsOf` for the keyboard, especially
   with edge-to-edge on Android 15+.
10. DO set a minimum window size on desktop (ADAPT-009), at least the compact
    width your layouts handle.

**Input**
11. DO make every hover affordance reachable without a mouse (ADAPT-008):
    show the action on touch, and on focus and long press. Use
    `FocusableActionDetector` for custom controls (focus, hover and
    shortcuts in one widget).
12. PREFER `Shortcuts` + `Actions` (or `CallbackShortcuts` for a few keys)
    for desktop and web shortcuts, with `SingleActivator` and the platform's
    modifier (`meta` on macOS, `control` elsewhere).
13. DO show scrollbars and allow mouse drag where users expect it
    (`Scrollbar`, `ScrollConfiguration` with `dragDevices`), right-click
    context menus (`GestureDetector(onSecondaryTapUp:)` opening a
    `MenuAnchor`, with the same menu on long press), and `SelectionArea`
    around readable text on web and desktop.

**Platform idioms**
14. DO use `Theme.of(context).platform` (or `defaultTargetPlatform`) for
    look and feel, and the `.adaptive` constructors (`Switch.adaptive`,
    `CircularProgressIndicator.adaptive`, `Slider.adaptive`,
    `showAdaptiveDialog`). DON'T read `dart:io` `Platform` in widgets or
    logic (ADAPT-001, ADAPT-002): it throws on the web and tests can't
    override it.
15. DO keep `kIsWeb` checks in sources and the composition root. A widget
    asks a source "is this supported", it doesn't branch on the platform to
    find out.

**Tests**
16. DO test each layout at its size classes: set `tester.view.physicalSize`
    and `devicePixelRatio`, and `addTearDown(tester.view.reset)` right after
    (ADAPT-010). Use `debugDefaultTargetPlatformOverride` (reset it before
    the test ends) or `ThemeData(platform: …)` for idioms.

## Reviewing

For a review, read `references/review.md`: the review checklist (every
finding ID with its severity and how to confirm it) and worked finding
examples in the suite's format. Writing code doesn't need it.

## Related skills

These assume the suite is installed as sibling folders. If your agent doesn't
auto-load skills, read the path given. If a sibling is missing, carry on and
say which check you skipped.

- **`flutter-navigation`** for `StatefulShellRoute` shells, routes, deep
  links and the web URL strategy (NAV-*). Fallback:
  `../flutter-navigation/SKILL.md`.
- **`flutter-design-system`** for where the breakpoint tokens live next to
  spacing and type, and component themes (DS-*). Fallback:
  `../flutter-design-system/SKILL.md`.
- **`flutter-accessibility`** for text scaling, tap targets, focus order and
  keyboard access (A11Y-*). Fallback: `../flutter-accessibility/SKILL.md`.
- **`flutter-performance`** for list and grid cost on large screens and
  rebuild scope (PERF-*). Fallback: `../flutter-performance/SKILL.md`.
- **`flutter-platform-integration`** for native capabilities behind a source,
  channels and plugins (PLAT-*). Fallback:
  `../flutter-platform-integration/SKILL.md`.
- **`flutter-ui-practices`** for widget lifecycle, `MediaQuery.sizeOf` and
  widget tests (UI-*). Fallback: `../flutter-ui-practices/SKILL.md`.
- **`flutter-testing`** for test strategy and goldens. Fallback:
  `../flutter-testing/SKILL.md`.
- **`flutter-architecture`** for detecting the pattern and the layer rules.
  Fallback: `../flutter-architecture/SKILL.md`.
- **`dart-flutter-review`** merges ADAPT findings into its report.

## References

| File | Read it when |
|---|---|
| `references/review.md` | reviewing: the checklist with every ID, severity and fix, and finding examples |
| `references/size-classes-and-layout.md` | defining breakpoints, choosing between `LayoutBuilder` and `MediaQuery.sizeOf`, switching bar/rail/drawer, building list-detail, handling foldables, orientation, safe areas and insets |
| `references/input-and-platform.md` | adding hover, focus, keyboard shortcuts, mouse scrolling, context menus or text selection; platform idioms and `.adaptive` widgets; desktop window sizing; web specifics |
| `references/placement-by-architecture.md` | deciding where the size classes, the layout decision, the selection and the capability checks go in MVN, MVVM, Bloc/Cubit, Clean, Provider, GetX or Riverpod |
| `references/testing-adaptive-layouts.md` | testing layouts per size class, goldens per size class, platform overrides, foldable and inset simulation |
| `references/rules.md` | every ADAPT rule: detection, why, fix, false positives; the reading-level slugs; what's checked elsewhere; calibration |
