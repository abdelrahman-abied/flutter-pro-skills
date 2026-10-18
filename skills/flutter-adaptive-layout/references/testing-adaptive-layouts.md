# Testing adaptive layouts

A layout that switches at a breakpoint has at least two behaviours; test
each one. Test strategy in general (which layer first, fakes vs mocks,
goldens) is `flutter-testing`'s; this file covers what is specific to size,
platform and input.

## Contents

1. Set the size, then reset it
2. One test per size class
3. Goldens per size class
4. Platform idioms
5. Foldables, insets and text scale
6. Input: hover, keyboard and right-click
7. Logic stays size-agnostic

## 1. Set the size, then reset it

flutter_test runs every test in a file in the same binding and does not
reset the test view between tests. A size set in one test leaks into the
next (ADAPT-010).

```dart
testWidgets('shows two panes when expanded', (tester) async {
  tester.view.physicalSize = const Size(2560, 1600);   // physical pixels
  tester.view.devicePixelRatio = 2;                    // 1280 x 800 logical
  addTearDown(tester.view.reset);                      // right after the change

  await tester.pumpWidget(const MaterialApp(home: InboxPage()));
  expect(find.byType(MessageDetail), findsOneWidget);
});
```

- `tester.view` replaces the deprecated `tester.binding.window.*TestValue`
  setters.
- `tester.binding.setSurfaceSize(size)` sets the logical size of the render
  surface; reset it with `addTearDown(() => tester.binding.setSurfaceSize(null))`.
- A helper that sets the size should either reset it itself
  (`addTearDown` inside the helper works) or be called by tests that reset.

## 2. One test per size class

Drive the same widget through the size classes with a table:

```dart
const sizes = {
  'compact': Size(390, 844),
  'medium': Size(700, 1000),
  'expanded': Size(1024, 768),
  'large': Size(1440, 900),
};

for (final MapEntry(key: name, value: size) in sizes.entries) {
  testWidgets('inbox layout ($name)', (tester) async {
    tester.view.devicePixelRatio = 1;
    tester.view.physicalSize = size;
    addTearDown(tester.view.reset);

    await tester.pumpWidget(const MaterialApp(home: AppShell()));
    final compact = size.width < 600;
    expect(find.byType(NavigationBar), compact ? findsOneWidget : findsNothing);
    expect(find.byType(NavigationRail), compact ? findsNothing : findsOneWidget);
  });
}
```

- Test the transitions too: pump at expanded, select an item, set the size
  to compact, `pump()`, and expect the same item to be shown (the bug in
  ADAPT-selection-lost-on-resize).
- Test the breakpoint edges (599 and 600, 839 and 840) once, against the
  size-class enum itself, not in every screen test.

## 3. Goldens per size class

- One golden per size class per screen catches layout regressions cheaply:
  `matchesGoldenFile('goldens/inbox_${name}.png')`.
- Goldens depend on fonts and the host OS; run them on one CI platform, and
  load real fonts (or use a package such as `alchemist`/`golden_toolkit` if
  the project already does).
- Keep goldens for screens, not for every small widget.

## 4. Platform idioms

- Switch the platform with the theme, or with the global override:

```dart
testWidgets('uses the iOS back icon', (tester) async {
  debugDefaultTargetPlatformOverride = TargetPlatform.iOS;
  await tester.pumpWidget(const MaterialApp(home: DetailScreen()));
  expect(find.byIcon(Icons.arrow_back_ios), findsOneWidget);
  debugDefaultTargetPlatformOverride = null;   // must be reset before the test ends
});

// or for every platform at once:
testWidgets('adapts', (tester) async { ... }, variant: TargetPlatformVariant.all());
```

- flutter_test fails the test if `debugDefaultTargetPlatformOverride` is
  still set at the end; reset it in the test body, not in `tearDown`.
- `TargetPlatformVariant.only(TargetPlatform.iOS)` and
  `TargetPlatformVariant.desktop()` / `.mobile()` run a test per platform.
- These overrides work only when the code reads `Theme.of(context).platform`
  or `defaultTargetPlatform`. Code that reads `dart:io` `Platform` can't be
  tested this way (ADAPT-002).
- Web-only behaviour behind `kIsWeb` is tested with `flutter test
  --platform chrome`, or by injecting the source that answers the question.

## 5. Foldables, insets and text scale

```dart
tester.view.displayFeatures = [
  const DisplayFeature(
    bounds: Rect.fromLTWH(590, 0, 20, 900),
    type: DisplayFeatureType.hinge,
    state: DisplayFeatureState.postureFlat,
  ),
];
tester.view.padding = const FakeViewPadding(top: 47, bottom: 34);  // notch and home indicator
tester.view.viewInsets = const FakeViewPadding(bottom: 300);       // keyboard
addTearDown(tester.view.reset);
```

- Combine the compact size with a large text scale
  (`MediaQuery(data: MediaQueryData(textScaler: TextScaler.linear(2)))`):
  that is where overflows hide. Text scaling itself is
  `flutter-accessibility`'s.

## 6. Input: hover, keyboard and right-click

```dart
// hover
final gesture = await tester.createGesture(kind: PointerDeviceKind.mouse);
await gesture.addPointer(location: Offset.zero);
addTearDown(gesture.removePointer);
await gesture.moveTo(tester.getCenter(find.byType(NoteTile)));
await tester.pump();

// keyboard shortcut
await tester.sendKeyDownEvent(LogicalKeyboardKey.metaLeft);
await tester.sendKeyEvent(LogicalKeyboardKey.keyF);
await tester.sendKeyUpEvent(LogicalKeyboardKey.metaLeft);

// right-click
await tester.tapAt(tester.getCenter(find.byType(NoteTile)), buttons: kSecondaryButton);
```

- For a hover affordance, also test that the action is reachable without
  hover: on `TargetPlatform.android` (touch) and by focusing it with Tab
  (`tester.sendKeyEvent(LogicalKeyboardKey.tab)`), which is the ADAPT-008
  bug.

## 7. Logic stays size-agnostic

- Notifier, view-model, bloc and controller tests never set a screen size.
  If a logic test needs one, the logic knows the layout (ADAPT-007): move
  the decision to the view.
- Test the size-class enum (`fromWidth`) with plain unit tests at the edges.
