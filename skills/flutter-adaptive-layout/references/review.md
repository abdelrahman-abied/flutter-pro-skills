# flutter-adaptive-layout: review checklist and finding examples

Moved out of `SKILL.md` so writing code doesn't load it: read this file
when you review code in this area, or when `dart-flutter-review` sends
you here. Paths are relative to the skill folder.

## REVIEW checklist

Script rules (`ADAPT-0xx`, full detail in `references/rules.md`):

| ID | Name | Default severity | What it catches |
|---|---|---|---|
| ADAPT-001 | io-platform-on-web | High | `dart:io` `Platform.isX`/`operatingSystem` in a widget, logic class or the app root of an app with `web/`, not guarded by `kIsWeb` (or a getter that checks it) |
| ADAPT-002 | platform-check-in-widget | Low | `Platform.isX` in a widget that ADAPT-001 doesn't cover (no web target, or guarded); was `PLAT-platform-check-in-widget` |
| ADAPT-003 | app-wide-orientation-lock | Medium (Info without android/ios) | `SystemChrome.setPreferredOrientations([portrait…])` at start-up with no size or platform condition |
| ADAPT-004 | magic-breakpoint | Low | width comparisons with literals 300–2000 (`constraints.maxWidth > 600`) that bypass the project's tokens, or repeat across files with no tokens |
| ADAPT-005 | device-identity-layout | Medium | `isTablet`/`isPhone` from the platform or the device model; `model.contains('iPad')` |
| ADAPT-006 | orientation-decides-layout | Low | `OrientationBuilder` or `orientationOf(context) == …` choosing a widget's layout |
| ADAPT-007 | screen-size-in-logic | Medium | a notifier, view model, bloc or controller reading `MediaQuery`/`View.of`/`Get.width`, or holding `screenWidth`/`isTablet`/a size-class field |
| ADAPT-008 | hover-only-action | Medium | a button shown only while a `MouseRegion` hover flag is true, with no focus or tap path |
| ADAPT-009 | desktop-window-unbounded | Low (once) | a desktop target (desktop folders plus desktop code or packages) with no minimum window size in Dart or the runner |
| ADAPT-010 | test-view-size-not-reset | Low | `tester.view.physicalSize`/`devicePixelRatio`/`setSurfaceSize` in a test with no reset |

Reading-level findings (`ADAPT-<slug>`; the checker can't see these):

| ID | Severity | Look for |
|---|---|---|
| ADAPT-selection-lost-on-resize | Medium | list-detail where widening or narrowing the window drops the selected item or the scroll position |
| ADAPT-insets-ignored | Medium | content under the notch, the system bars or the keyboard; edge-to-edge without `SafeArea` or `viewInsetsOf` |
| ADAPT-content-under-hinge | Medium | a two-pane layout that ignores `displayFeaturesOf` on foldables |
| ADAPT-no-shortcuts | Medium | a desktop or web app whose primary actions have no keyboard shortcut (focusability itself is A11Y-no-keyboard-access) |
| ADAPT-mediaquery-for-component | Low | `MediaQuery.sizeOf` sizing a widget that lives in a pane, a dialog or a list item; use `LayoutBuilder` |
| ADAPT-nav-not-adaptive | Low | a `NavigationBar` on every width, or a rail on phones |
| ADAPT-unbounded-content-width | Low | text, forms or cards stretched across a 1600 dp window |
| ADAPT-fixed-screen-size | Low | `SizedBox(width: 375, height: 812)` and similar boxes that hard-code one phone |
| ADAPT-no-desktop-scrolling | Low | horizontal lists that a mouse can't scroll (no `Scrollbar`, no drag devices), or missing scrollbars on desktop |
| ADAPT-no-context-menu | Low | desktop and web lists with no right-click or long-press menu where the platform expects one |
| ADAPT-text-not-selectable | Low | readable text on web or desktop not wrapped in `SelectionArea` |
| ADAPT-non-adaptive-control | Low | `Switch`, `CircularProgressIndicator` or dialogs not `.adaptive` in an app that follows platform idioms |
| ADAPT-kisweb-scattered | Low | `kIsWeb` branches spread across widgets instead of sources and the composition root |
| ADAPT-no-size-class-tests | Low | adaptive screens tested only at the default 800×600 test size |

**Don't report here (cross-reference instead):**
- `MediaQuery.of(context).size` instead of `sizeOf`: the `mediaquery-of`
  heuristic and `UI-*` (`flutter-ui-practices`). ADAPT-006 wins only when
  the same line reads the orientation to choose a layout.
- Physical `left`/`right` geometry: I18N-012. Magic spacing: DS-003. Text
  scaling and fixed heights around text: A11Y-004 / A11Y-006. Tap-target
  size: A11Y-005. Custom controls that can't be focused: A11Y-no-keyboard-access.
- Eager lists: PERF-001. Navigation shells, routes and web URL strategy:
  NAV and `flutter-navigation`. `BuildContext` in logic: ARCH-102 (ADAPT-007
  reports the size knowledge, not the context). Store target SDK: REL.
- Platform channels in widgets: PLAT-001. ADAPT-002 owns only the
  platform *check*.

**When not to flag:**
- A component's own minimum inside `LayoutBuilder` (a card that wraps its
  chips under 280 dp) is not a window breakpoint; suppress it with a reason.
- `Platform` behind `kIsWeb` (`kIsWeb || !Platform.isX`, `if (kIsWeb) return`,
  a getter such as `static bool get isDesktop => !kIsWeb && …`), in a file
  picked by an `if (dart.library.io)` conditional import, or in a
  platform-specific file (`*_desktop.dart`, `android/`, `window/`).
- An orientation lock on one screen that restores `DeviceOrientation.values`
  on dispose, or a lock guarded by the shortest side.
- A layout notifier whose job is the breakpoint (`BreakpointNotifier`): it
  is UI infrastructure, not feature logic.

## Finding examples

Use the suite's finding format (`dart-flutter-review` merges them):

```markdown
### [HIGH] Platform.isIOS crashes the feed on the web
- id: ADAPT-001
- where: lib/features/feed/presentation/view/feed_view.dart:31
- evidence: `final back = Platform.isIOS ? Icons.arrow_back_ios : Icons.arrow_back;` (the app has web/)
- rule: never read dart:io Platform in UI (flutter-adaptive-layout › rules.md ADAPT-001)
- why: every Platform getter throws UnsupportedError on the web, so the screen fails to build there
- fix: |
    final back = Theme.of(context).platform == TargetPlatform.iOS ? Icons.arrow_back_ios : Icons.arrow_back;
- confidence: confirmed

### [MEDIUM] Delete only appears on mouse hover
- id: ADAPT-008
- where: lib/features/notes/presentation/widgets/note_tile.dart:42
- evidence: `if (_hovered) IconButton(icon: Icon(Icons.delete), ...)`; `_hovered` is set only in MouseRegion onEnter/onExit
- rule: every hover affordance has a touch and keyboard path (flutter-adaptive-layout › rules.md ADAPT-008)
- why: on phones, tablets and with a keyboard the delete action can never be reached
- fix: |
    final touch = switch (Theme.of(context).platform) { TargetPlatform.android || TargetPlatform.iOS => true, _ => false };
    if (touch || _hovered || _focused) IconButton(...)   // _focused from FocusableActionDetector.onShowFocusHighlight
- confidence: confirmed
```

Open the report with one line naming the profile, the targets and the
breakpoint tokens (`mvvm, android/ios/web, no size classes`). Report a
pattern-wide issue (for example, eight screens each with their own `> 600`)
**once**, with a few locations and the token to introduce.
