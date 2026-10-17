# Testing accessibility

Automated checks catch missing labels, small targets and low contrast on
every run. A short manual pass with a real screen reader catches the rest:
reading order, confusing labels and silent results. Do both. Widget-test
structure, fakes and pumping belong to `flutter-testing` (or read
`../flutter-testing/SKILL.md`).

## Contents

1. Guideline tests
2. Semantics assertions
3. Text scale and motion tests
4. Manual checklist (TalkBack, VoiceOver, Scanner, Inspector)

## 1. Guideline tests

`flutter_test` ships four guidelines. Run them on every screen's widget test,
with the semantics tree switched on.

```dart
testWidgets('home screen meets accessibility guidelines', (tester) async {
  final handle = tester.ensureSemantics();
  await tester.pumpWidget(const MaterialApp(home: HomeScreen()));

  await expectLater(tester, meetsGuideline(androidTapTargetGuideline));   // 48x48 dp
  await expectLater(tester, meetsGuideline(iOSTapTargetGuideline));       // 44x44 pt
  await expectLater(tester, meetsGuideline(labeledTapTargetGuideline));   // every tappable has a label
  await expectLater(tester, meetsGuideline(textContrastGuideline));       // WCAG AA text contrast

  handle.dispose();
});
```

- Pump the screen with fakes for its dependencies (fake repository, overridden
  providers, a mocked bloc state), as `flutter-testing` describes.
- Run the guidelines in light and dark themes, and once per important state
  (empty, loaded, error).
- `textContrastGuideline` measures rendered text against what's painted
  behind it, so it can't see text drawn on images. Check those by hand.
- A `MinimumTapTargetGuideline(size: Size(48, 48), link: …)` or a custom
  `AccessibilityGuideline` can encode a house rule.

## 2. Semantics assertions

Find widgets the way assistive technology does, by label:

```dart
final handle = tester.ensureSemantics();
await tester.pumpWidget(app);

expect(find.bySemanticsLabel('Delete todo'), findsOneWidget);
expect(find.bySemanticsLabel(RegExp(r'^3 unread')), findsOneWidget);

expect(
  tester.getSemantics(find.byType(LikeButton)),
  matchesSemantics(label: 'Like', isButton: true, hasTapAction: true, hasEnabledState: true, isEnabled: true),
);

// secrets never reach the tree
expect(find.bySemanticsLabel(RegExp('123456')), findsNothing);
handle.dispose();
```

- `containsSemantics(...)` checks only the properties you name, which
  survives framework changes better than `matchesSemantics`.
- `tester.semantics.find(...)` and `SemanticsFinder` (newer SDKs) query the
  semantics tree directly.
- The framework's own tests use `SemanticsTester` and `TestSemantics` to
  compare whole trees. It works in app tests too, but it is brittle; keep it
  for custom render objects and complex components.
- **Announcements.** Capture them with the test binding's
  `SystemChannels.accessibility` mock, or (newer SDKs)
  `tester.takeAnnouncements()`, and assert the localised text was announced
  once.

```dart
final announced = <String>[];
tester.binding.defaultBinaryMessenger.setMockDecodedMessageHandler<dynamic>(
  SystemChannels.accessibility,
  (message) async {
    final data = (message as Map)['data'] as Map;
    if (data['message'] != null) announced.add(data['message'] as String);
  },
);
// ... trigger the save ...
expect(announced, ['Profile saved']);
```

## 3. Text scale and motion tests

```dart
testWidgets('checkout survives 200% text', (tester) async {
  tester.platformDispatcher.textScaleFactorTestValue = 2.0;
  addTearDown(tester.platformDispatcher.clearTextScaleFactorTestValue);
  await tester.pumpWidget(app);
  expect(tester.takeException(), isNull);   // no RenderFlex overflow
});

testWidgets('carousel stops when animations are disabled', (tester) async {
  await tester.pumpWidget(MediaQuery(
    data: const MediaQueryData(disableAnimations: true),
    child: app,
  ));
  // assert the reduced-motion path
});
```

Golden tests at 1.0 and 2.0 text scale make layout regressions visible.

## 4. Manual checklist

Run this before a release and after any change to navigation or a shared
component. It takes ten minutes per main flow.

**TalkBack (Android)** and **VoiceOver (iOS)**:
- [ ] Swipe through each screen. Every control is reached, in a sensible
      order, with a name and a role ("Delete, button").
- [ ] No unlabelled "button" or "image" announcements; no file names read.
- [ ] Headings are announced as headings and the heading rotor/menu jumps
      between them.
- [ ] Results, errors and loading completion are announced (live region or
      announcement).
- [ ] Dialogs and sheets keep focus inside, and focus returns to the trigger
      on close.
- [ ] No password, code, token or card number is ever read aloud.
- [ ] Custom controls (switches, sliders, steppers) report their state and
      respond to the standard gestures (double tap, swipe up/down on sliders).

**Display settings:**
- [ ] Largest font size (200 %+): nothing clipped, overlapped or cut off with
      no way to read it.
- [ ] Bold text, high-contrast text and dark mode still meet contrast.
- [ ] "Remove animations" / "Reduce motion": no parallax or auto-play.
- [ ] Colour filters or greyscale: status is still clear without colour.

**Input:**
- [ ] Keyboard (desktop, web, or a tablet keyboard): Tab reaches every
      control in order, focus is visible, Enter/Space activate.
- [ ] Switch Access (Android) or Switch Control (iOS) can reach and activate
      every control.
- [ ] Voice Access / Voice Control: every control has a name you can say.

**Tools:**
- Android **Accessibility Scanner**: scans the running screen for small
  targets, missing labels and low contrast.
- Xcode **Accessibility Inspector**: inspects labels and traits and runs an
  audit on the iOS simulator.
- Flutter DevTools' widget inspector and `showSemanticsDebugger: true` show
  the semantics tree inside the app.
- Chrome DevTools' accessibility pane for Flutter web (enable semantics with
  the "Enable accessibility" placeholder or `SemanticsBinding.instance.ensureSemantics()`).
