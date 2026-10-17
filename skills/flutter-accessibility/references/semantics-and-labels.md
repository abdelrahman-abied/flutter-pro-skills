# Semantics and labels

Flutter renders its own pixels, so TalkBack, VoiceOver, switch access and
voice control only see the **semantics tree** that the framework builds next
to the widget tree. Material and Cupertino widgets fill it in for you. Custom
widgets, icons and images often don't. This file covers how to label what you
build, how to shape the tree so it reads well, and how to keep secrets out
of it.

You can see the tree while the app runs: turn on
`MaterialApp(showSemanticsDebugger: true)` or call `debugDumpSemanticsTree()`.

## Contents

1. Icon buttons and tooltips
2. Custom tappables
3. Images and icons
4. Shaping the tree (Merge, Exclude, Block, container, header)
5. Live regions and announcements
6. Secrets and PII in semantics
7. Labels come from l10n

## 1. Icon buttons and tooltips

An `IconButton` has the button role, focus handling, keyboard activation and
a 48 dp target. What it lacks is a name. `tooltip:` gives it one. The tooltip
becomes the semantic label, and sighted users see it on long press or hover.

```dart
// BAD: TalkBack says "Button"
IconButton(icon: const Icon(Icons.delete), onPressed: onDelete)

// GOOD
IconButton(
  icon: const Icon(Icons.delete),
  tooltip: AppLocalizations.of(context).deleteTodo,
  onPressed: onDelete,
)
```

The same goes for a `FloatingActionButton` whose child is an icon. A
`FloatingActionButton.extended(label: Text(…))` is already labelled.

**Put it in the component.** If the app has its own `AppIconButton`, make
`tooltip` (or `semanticLabel`) a **required** `String` parameter. Then every
call site has to supply it, and the checker has nothing to find. A wrapper
whose `tooltip` is optional (`String?`) is judged at each call site
(A11Y-001).

`Icon(semanticLabel:)` works too, but prefer `tooltip:` on the button, because
it also helps sighted users.

## 2. Custom tappables

`GestureDetector` and `InkWell` add a tap action to the tree but no role and
no name. Around a `Text` that's usually fine, because the text names it. Around
an icon or an image it's an unnamed blob.

```dart
// BAD
InkWell(onTap: onLogout, child: const Icon(Icons.logout))

// GOOD: give it the role and the name
Semantics(
  button: true,
  label: l10n.logout,
  child: InkWell(onTap: onLogout, child: const Icon(Icons.logout)),
)

// BETTER: use the widget that already does this
IconButton(icon: const Icon(Icons.logout), tooltip: l10n.logout, onPressed: onLogout)
```

For controls that aren't buttons, set the matching flag and actions:
`Semantics(toggled: isOn, onTap: toggle)` for a switch,
`Semantics(checked: isChecked, …)` for a checkbox, and
`Semantics(slider: true, value: '40%', increasedValue: '50%', onIncrease: …,
onDecrease: …)` for a slider. `FocusableActionDetector` adds keyboard focus,
hover and shortcuts in one widget (see `visual-and-input.md` §4).

If a gesture is handled by a parent `Semantics(onTap:)`, set
`excludeFromSemantics: true` on the inner `GestureDetector` so the action
isn't exposed twice. Without that parent, `excludeFromSemantics: true` hides
the action completely (A11Y-009).

## 3. Images and icons

Every image is either content or decoration. Decide each one:

```dart
Image.network(user.avatarUrl, semanticLabel: l10n.profilePhotoOf(user.name))   // content
Image.asset('assets/wave.png', excludeFromSemantics: true)                     // decoration
SvgPicture.asset('assets/logo.svg', semanticsLabel: l10n.appName)               // flutter_svg spells it semanticsLabel
```

A label describes what matters ("Map of the route"), not the file ("image",
"photo123.png"). Don't start with "Image of"; the reader already says it's an
image. An image inside a labelled button needs no label of its own.

Icons drawn with `Icon` are skipped by screen readers unless they have a
`semanticLabel`. That's right for icons next to text. For a status icon that
stands alone (a warning triangle, a "verified" tick), add the label.

## 4. Shaping the tree

- **`MergeSemantics`** turns a subtree into one node. Use it for a row of
  icon plus text plus value that the user should hear as one item. Don't
  merge two separate controls; the user can then reach only one of them.
- **`ExcludeSemantics`** drops a subtree. Use it for duplicates (a decorative
  copy of a title, a badge already read in the label) and decoration. Never
  wrap a control in it (A11Y-009). `excluding: condition` is fine for content
  that is hidden only some of the time.
- **`BlockSemantics`** hides everything painted *before* it in the same layer.
  Custom dialogs and drawers use it so the reader can't wander behind them.
  Material dialogs already do this.
- **`Semantics(container: true)`** makes a boundary, so a card's content is
  explored as a group without being merged into one string.
- **`Semantics(header: true)`** marks section titles. Screen-reader users
  jump between headings, the way sighted users scan.
- **`Semantics(sortKey: OrdinalSortKey(n))`** adjusts reading order when the
  visual layout differs from the build order. Prefer fixing the build order.
- **`Semantics(identifier: …)`** gives test tools and native test drivers a
  stable handle. It isn't read aloud.

## 5. Live regions and announcements

When something changes without a page transition (a search returns, a save
fails, a timer ends), a screen-reader user needs to hear it.

- **Live region**: wrap the changing text in `Semantics(liveRegion: true)`.
  The platform re-reads it when its label changes. Good for status lines and
  inline errors.
- **Announcement**: `SemanticsService.announce(message, textDirection)` for a
  one-time event without a visible line (an item was added to the cart, a
  background upload finished). Newer Flutter versions also offer
  `SemanticsService.sendAnnouncement(view, message, textDirection)`; use
  whichever the project's SDK provides.

Announce from the view, never from logic (A11Y-011). The message must be
localised and needs the current text direction, and both come from the
`BuildContext`. Logic emits the fact; the view's listener speaks it. See
`placement-by-architecture.md` for the code per pattern.

```dart
SemanticsService.announce(l10n.itemAdded(item.name), Directionality.of(context));
```

Keep announcements short and rare. Announcing every keystroke or every list
update drowns out everything else.

## 6. Secrets and PII in semantics

Whatever is in the tree is spoken aloud, shown in braille displays, and
delivered as text to every enabled accessibility service. Some of those
services are malware that asks for the permission to read the screen.

- **DO** keep `obscureText: true` on secret fields. Flutter then exposes the
  field as obscured and never puts the value in the tree. Checking
  `obscureText` itself is FORM-001's job (`flutter-forms`).
- **DON'T** copy a password, PIN, OTP, token, CVV or recovery phrase into
  `Semantics(label:)`, `Semantics(value:)`, `Text(semanticsLabel:)` or an
  announcement (A11Y-007). Describe the state instead:

```dart
// BAD
Semantics(value: _otpController.text, child: const OtpBoxes())
SemanticsService.announce('Your code is $otp', TextDirection.ltr);

// GOOD
Semantics(value: l10n.digitsEntered(_otpController.text.length, 6), child: const OtpBoxes())
SemanticsService.announce(l10n.codeFilled, Directionality.of(context));
```

- **AVOID** announcing personal data (names, balances, addresses, health
  details) on screens that may be used in public. Announce the event
  ("Payment sent") and let the user explore the details.
- **CONSIDER** the platform's secure-screen flags and accessibility-overlay
  defences for banking and health apps. `flutter-security-audit` covers
  them (if installed).

## 7. Labels come from l10n

A label is user-facing text, so it goes through the same gen-l10n, ARB or
intl pipeline as every other string. Plurals and counts use ICU messages
(`{count, plural, =1{1 unread message} other{{count} unread messages}}`) so
"1 unread messages" never reaches a screen reader. A non-localised label is
I18N-010 (`flutter-i18n`); this skill only flags a *missing* one.
