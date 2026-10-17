# Visual and input accessibility

Not every accessibility user runs a screen reader. Many more use larger text,
need bigger targets, read poorly contrasted text with difficulty, navigate by
keyboard or switch, or get dizzy from motion. This file covers those settings.

## Contents

1. Tap targets
2. Contrast
3. Text scale
4. Focus, keyboard and switch access
5. Reduced motion and colour-only meaning

## 1. Tap targets

Material asks for **48x48 dp**, Apple for **44x44 pt**. The visible icon can
be smaller; the hit area can't.

- Material buttons already pad themselves to 48 dp through
  `MaterialTapTargetSize.padded`. `MaterialTapTargetSize.shrinkWrap` (in
  `ThemeData.materialTapTargetSize` or a button's `tapTargetSize`) removes
  that padding (A11Y-005). Keep `padded` unless the control sits in a dense
  desktop layout that has keyboard access.
- A tight parent shrinks the hit area too:
  `SizedBox(width: 24, height: 24, child: IconButton(…))` gives a 24 dp
  target, whatever the button's own minimum. Let the button size itself, and
  use `iconSize` and `visualDensity` for the look.
- `IconButton(constraints: BoxConstraints(), padding: EdgeInsets.zero)`
  shrinks the button to the icon. Use it only inside a parent that is itself
  at least 48 dp and tappable.
- `visualDensity: VisualDensity.compact` reduces the visual size. In Material
  3 the padded tap target still applies, but check with
  `androidTapTargetGuideline` before relying on that.
- For `GestureDetector`/`InkWell`, make the child at least 48x48 (padding or
  `ConstrainedBox(constraints: BoxConstraints(minWidth: 48, minHeight: 48))`)
  and use `behavior: HitTestBehavior.opaque` so the whole box responds.
- Keep at least 8 dp between adjacent targets.

## 2. Contrast

WCAG 2.x AA, which most app-store and legal guidance cites:

| Content | Minimum ratio |
|---|---|
| body text (under 18 pt, or under 14 pt bold) | 4.5:1 |
| large text (18 pt+, or 14 pt+ bold) | 3:1 |
| icons, focus rings, control borders, chart lines | 3:1 |
| disabled controls, pure decoration | no requirement |

**How the ratio is computed** (this is what A11Y-008 does):

```
channel c (0–1) → linear: c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ^ 2.4
relative luminance L = 0.2126 R + 0.7152 G + 0.0722 B
ratio = (L_lighter + 0.05) / (L_darker + 0.05)
```

White on Material red (`#F44336`) is 3.68:1. That's fine for a large icon but
not for body text. White on `#E4935D` is 2.43:1, which fails everything.

**In Flutter, contrast lives in the `ColorScheme`.** Every `onX` colour is
drawn on its `X` colour: `onPrimary` on `primary`, `onSurface` on `surface`,
`onError` on `error`, `onPrimaryContainer` on `primaryContainer`, and so on.
Check each pair in light *and* dark mode.

- `ColorScheme.fromSeed(seedColor:)` computes accessible on-colours for you.
  Overriding single roles (`primary: brandOrange`) without the matching `onX`
  is where contrast breaks.
- Text drawn with `onSurfaceVariant` or with opacity (`withValues(alpha: .6)`)
  on `surface` is a common failure. Compute it.
- Token structure (where colours are defined, `ThemeExtension`s, no raw
  colours in features) belongs to `flutter-design-system` (or read
  `../flutter-design-system/SKILL.md`). This skill judges the ratios.
- Test it: `expect(tester, meetsGuideline(textContrastGuideline))` checks the
  rendered text (see `testing-accessibility.md`).

## 3. Text scale

Android and iOS let users raise the font size to about 200 % (and further
with accessibility sizes). Flutter applies it through `TextScaler`.

- **DON'T** switch it off for the whole app. `TextScaler.noScaling`,
  `textScaleFactor: 1.0` or `TextScaler.linear(1)` in `MaterialApp.builder`
  makes the app unreadable for low-vision users (A11Y-004, high).
- **AVOID** clamping below 2.0. `MediaQuery.withClampedTextScaling(maxScaleFactor: 1.3)`
  is still "disabled" for anyone who needs 200 %. If a few layouts break, fix
  those layouts. If you clamp, clamp locally, at 2.0 or more.
- Read the scaler with `MediaQuery.textScalerOf(context)` and scale custom
  measurements with `textScaler.scale(fontSize)`. `textScaleFactor` is
  deprecated because the platforms scale non-linearly.
- **Avoid fixed heights around text** (A11Y-006). Use `minHeight`,
  padding, `Flexible`/`Expanded` and wrapping. Allow two lines for buttons.
  `maxLines` plus `overflow: TextOverflow.ellipsis` is acceptable for list
  titles that open a detail screen, not for unique information.
- A fixed-size glyph (a game piece, a clock numeral, a logo wordmark) can opt
  out locally with a `TextScaler.noScaling` and an `a11y-ignore` reason, as
  long as the information is available as scalable text elsewhere.
- Test at 200 %: `tester.platformDispatcher.textScaleFactorTestValue = 2.0`,
  or wrap the screen in `MediaQuery(data: MediaQueryData(textScaler:
  TextScaler.linear(2)), …)`, then check for overflow errors.

## 4. Focus, keyboard and switch access

Keyboard, switch-control and voice-control users move focus from control to
control. Flutter's `Focus` system handles it; custom widgets have to take part.

- **Order.** The default `ReadingOrderTraversalPolicy` follows the layout.
  Group related controls with `FocusTraversalGroup`, and set an explicit order
  with `FocusTraversalOrder(order: NumericFocusOrder(n))` plus
  `OrderedTraversalPolicy` only when the visual order isn't the logical one.
- **Activation.** Custom controls should react to Enter and Space. Use
  `FocusableActionDetector(actions: {ActivateIntent: CallbackAction(onInvoke: …)},
  onShowFocusHighlight: …, child: …)`, or `Shortcuts` plus `Actions` for
  app-wide shortcuts.
- **Visible focus.** Show a focus ring or colour change when
  `onShowFocusHighlight` reports true. Material widgets do this already; a
  custom `GestureDetector` card doesn't.
- **`autofocus`.** At most one widget per screen (A11Y-010). On a screen
  reader, autofocus moves the reader's cursor too, so use it where the user
  expects it (a search screen's field), not on every form.
- **Modals.** Dialogs and bottom sheets trap focus and return it to the
  trigger on close. Material ones do; custom overlays need a `FocusScope` and
  `BlockSemantics`.
- **Focus nodes** are owned and disposed by the widget `State`, never by
  logic (`flutter-forms` and ARCH-109).

## 5. Reduced motion and colour-only meaning

**Reduced motion.** `MediaQuery.disableAnimationsOf(context)` is true when the
user turned on "Remove animations" (Android) or "Reduce motion" (iOS).

```dart
final reduce = MediaQuery.disableAnimationsOf(context);
AnimatedSwitcher(
  duration: reduce ? Duration.zero : const Duration(milliseconds: 300),
  child: child,
);
```

Skip parallax, auto-playing carousels and large zooms, or replace them with a
cross-fade. Essential motion (a progress indicator) can stay. Read the
setting in the view or in the design system's motion tokens, never in logic.

**Colour-only meaning.** Don't show status only by colour: red error borders,
green "online" dots, or chart series told apart only by hue. Add an icon,
text, a pattern or a `Semantics(value:)`. Input errors use `errorText`, which
both shows and announces the message.
