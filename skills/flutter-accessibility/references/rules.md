# A11Y rules: what the checker reports, and why

`scripts/check_accessibility.py` is static and read-only. It needs only the
Python standard library and no `pub get`. Every hit is a candidate: read the
code before you call a finding `confirmed`. Each rule lists the false
positives it knows about. The rules were calibrated on flutter/samples
(`compass_app`), every bloclibrary and Riverpod example, wonderous, lichess
and immich (see §4).

## Contents

1. How labels and wrappers are recognised
2. A11Y-001 … A11Y-011
3. Reading-level findings (A11Y-<slug>)
4. Calibration
5. What this skill deliberately doesn't check (and who does)

## 1. How labels and wrappers are recognised

The widget tree is read as the nesting of constructor calls inside one
expression. A control counts as **labelled** when any of these holds:

- it has its own `tooltip:`, or its icon or image has `semanticLabel:` /
  `semanticsLabel:` / `imageSemanticLabel:`;
- an enclosing call is `Semantics(label:/value:)`, `Semantics(excludeSemantics:
  true)`, `Tooltip`, `MergeSemantics`, `ExcludeSemantics` or `BlockSemantics`;
- an enclosing call passes `tooltip:`, `label:`, `semanticLabel:` or
  `semanticsLabel:` (`NavigationDestination`, `ElevatedButton.icon`,
  `Chip`, project buttons). `InputDecoration` doesn't count: a field's label
  doesn't name its suffix button;
- one hop away: the control is stored in a local variable, or returned by a
  helper method, that is used inside a labelled call.

**Wrappers** are project widgets found across all files:

- a *label wrapper* forwards an optional `String?` field to an `IconButton`'s
  `tooltip:`. Its calls that don't pass that field are A11Y-001.
- a *scale wrapper* builds `TextScaler.linear(field)` with a default of 1.3 or
  less. Its calls that don't pass the field are A11Y-004.
- an `IconButton(icon: icon)` that forwards a widget parameter is judged at
  its call sites: it's reported only if some call passes an unlabelled icon.

The text report lists the wrappers it found.

## 2. Rules

### A11Y-001 icon-button-without-label

**Medium** · all profiles

**Detects:** `IconButton` (`.filled`, `.filledTonal`, `.outlined`) and
`FloatingActionButton` (`.small`, `.large`) whose child is an icon, with no
`tooltip:` and not labelled (§1). Also calls to a label wrapper that leave
out the forwarded tooltip.
**Why:** TalkBack and VoiceOver announce "button" and nothing else. Voice
Control users can't name it.
**Bad / good:**

```dart
IconButton(icon: const Icon(Icons.share), onPressed: share)                       // bad
IconButton(icon: const Icon(Icons.share), tooltip: l10n.share, onPressed: share)  // good
```

**Profile notes:** none; labels live in the view in every pattern.
**False positives:** a button labelled by a `Semantics` in a *different*
widget class that wraps this one. Calibration fixed the same-file shapes
(helper methods, local variables, forwarded icons). Suppress the rest with
the reason.

### A11Y-002 tappable-without-label

**Medium** · all profiles

**Detects:** `GestureDetector`, `InkWell`, `InkResponse`, `CupertinoButton`
or `RawMaterialButton` with a handler, whose only child (looking through
`Padding`, `Center`, `SizedBox`, `Container`, `DecoratedBox`, `ClipOval`…) is
an `Icon`, `ImageIcon`, `Image`, `SvgPicture` or `CircleAvatar` without a
label, and that isn't labelled (§1).
**Why:** the reader finds an unnamed element with a tap action and no role.
**Fix:** `Semantics(button: true, label: …)` around it, or an `IconButton`
with a tooltip (`semantics-and-labels.md` §2).
**False positives:** none found in calibration. A custom tappable with a
`Semantics` parent defined in another file is the expected one.

### A11Y-003 image-without-semantics

**Low** · all profiles

**Detects:** `Image`, `Image.asset/network/file/memory`, `SvgPicture.*` and
`FadeInImage` with neither a label argument nor `excludeFromSemantics`
(anything but `false`), unless labelled or excluded by an enclosing call, or
the child of a tappable already reported as A11Y-002.
**Why:** the checker can't know whether an image is content or decoration,
so the finding asks you to decide. A meaningful image without a label loses
its information; a decorative one should be marked so.
**Fix:** `semanticLabel: l10n.…` for content, `excludeFromSemantics: true`
for decoration.
**False positives:** decorative images inside a labelled parent in another
file. Low severity on purpose.

### A11Y-004 text-scaling-disabled

**High** when app-wide, **Medium** locally, **Low** for clamps between 1.3
and 2.0 · all profiles

**Detects:** `TextScaler.noScaling`, `MediaQuery.withNoTextScaling(`,
`textScaleFactor: <≤1.3>`, `TextScaler.linear(<≤1.3>)`, `maxScaleFactor:
<2.0` and `textScaleFactor.clamp(_, <2.0)`, plus calls to scale wrappers
(§1). App-wide means inside a `*App(builder:)`, a `MediaQuery` that wraps
`MaterialApp`/`CupertinoApp`, or `lib/main*.dart`.
**Why:** users who need 200 % text can't read the app. WCAG 1.4.4 asks for
200 % without loss of content.
**Bad / good:**

```dart
builder: (context, child) => MediaQuery(
  data: MediaQuery.of(context).copyWith(textScaler: TextScaler.noScaling), child: child!)  // bad
builder: (context, child) => child!            // good: fix the layouts that overflow instead
```

**False positives:** fixed-size glyphs and dials that have a scalable text
alternative (lichess's tab bar copies iOS, which shows labels in the Large
Content Viewer instead; Flutter has no such viewer, so it stays a finding).
Suppress with the reason.

### A11Y-005 tap-target-too-small

**Medium** below 44 dp, **Low** from 44 to 47 dp and for `shrinkWrap` · all profiles

**Detects:** `MaterialTapTargetSize.shrinkWrap`; a `SizedBox`,
`SizedBox.square`, `SizedBox.fromSize` or `Container` with a literal width or
height under 48 whose child (through one wrapper) is a button, gesture
detector, ink well, checkbox, radio or switch with a handler.
**Why:** small targets are hard to hit with tremor, limited dexterity or a
thumb. `androidTapTargetGuideline` fails them.
**Fix:** let the control size itself (48 dp), keep
`MaterialTapTargetSize.padded`, and shrink only the visual.
**False positives:** dense desktop-only layouts with full keyboard access.

### A11Y-006 fixed-height-around-text

**Low** · all profiles

**Detects:** a `SizedBox` or `Container` with a literal `height:` under 40
whose child (through one wrapper) is `Text`, `Text.rich`, `SelectableText`,
`RichText` or `AutoSizeText`.
**Why:** at 200 % a 14 sp line needs about 40 dp. The text clips or
overflows.
**Fix:** `ConstrainedBox(constraints: BoxConstraints(minHeight: h))`,
padding, or no height at all.
**False positives:** single glyphs or numbers whose box is meant to clip.

### A11Y-007 secret-in-semantics

**High** · all profiles

**Detects:** a `Semantics(label:/value:/hint:/increasedValue:/decreasedValue:)`,
a `semanticsLabel:`/`semanticLabel:`/`semanticsValue:` argument, or the
message of `SemanticsService.announce`/`sendAnnouncement`, whose identifiers
(including string interpolations) name a password, PIN, OTP, token, CVV,
secret, API or private key, or credential. Identifiers that also say *label,
hint, title, error, length, count, visible, obscure, status…* and l10n
receivers (`l10n.passwordLabel`, `S.of(context).pin`) don't count; nor do
`.length` and `.isEmpty`.
**Why:** the reader speaks the value aloud, braille displays show it, and
every accessibility service receives it as text.
**Fix:** describe the state: `l10n.digitsEntered(code.length, 6)`,
`l10n.codeFilled`.
**Profile notes:** for announcements, the `note` gives the pattern's way to
announce from the view (MVN `ref.listen`, Bloc `BlocListener`, MVVM command
listener, GetX `ever()`).
**False positives:** a variable named like a secret that holds something
else (`tokenCount` is already excluded). Suppress with the reason.

### A11Y-008 low-contrast-color-scheme

**Medium** · all profiles

**Detects:** in `ColorScheme(`, `.light(`, `.dark(`, `.fromSeed(` and
`.highContrastLight/Dark(`, an `X` / `onX` pair (`primary`/`onPrimary`,
`surface`/`onSurface`, `error`/`onError`, the containers,
`inverseSurface`…) where both colours resolve to opaque literals and the WCAG
contrast ratio is below 4.5:1. Colours resolve from `Color(0xAARRGGBB)`,
`Color.fromARGB`, `Colors.<name>` (the 500 shades, white and black) and
project constants defined that way (`static const brand = Color(…)`, by last
name segment). Anything unresolved, ambiguous or translucent is skipped.
**Why:** text drawn with `onX` on `X` is hard to read for low-vision users and
in sunlight. The note gives the ratio and whether it also fails 3:1.
**Fix:** choose an on-colour that reaches 4.5:1, or let
`ColorScheme.fromSeed` compute it (`visual-and-input.md` §2).
**False positives:** a role the app never draws text with. Suppress with the
reason, or set a matching on-colour anyway: Material components will use it.

### A11Y-009 exclude-semantics-hides-control

**Medium** · all profiles

**Detects:** `ExcludeSemantics` (no `excluding:` or `excluding: true`) whose
subtree contains a button, gesture detector, ink well, text field, checkbox,
switch, slider, radio, dropdown, popup menu or list tile with a handler; and
`GestureDetector`/`RawGestureDetector`/`InkWell` with
`excludeFromSemantics: true` and an `onTap`. Skipped when an enclosing
`Semantics` has `onTap`, `button: true` or `link: true`, or an enclosing
button handles the tap.
**Why:** the control disappears for screen readers and switch access.
**Fix:** remove the exclusion, or expose the action on a parent
`Semantics(button: true, label: …, onTap: …)`.
**False positives:** calibration found `ExcludeSemantics(excluding:
!isFocused)` around a collapsed search field (riverpod `marvel`); a
non-literal `excluding:` is now skipped (fixture `calib_riverpod_marvel`).

### A11Y-010 multiple-autofocus

**Low** · all profiles

**Detects:** a second `autofocus: true` in the same class, unless the two are
alternatives (different branches of `?:`, `if`/`else`, `switch`, or separate
closures).
**Why:** only one widget can take focus; which one wins is an
implementation detail, and the reader's cursor jumps.
**Fix:** keep one `autofocus`, or move focus explicitly with a `FocusNode`.
**False positives:** calibration found two fields in the branches of a
ternary in an immich dialog; branch detection was added (fixture
`calib_immich`).

### A11Y-011 announcement-in-logic

**Medium** · mvn, mvvm, bloc, getx, provider, riverpod, mvc (any file with
the `logic` or `state` role)

**Detects:** `SemanticsService.announce(` or `sendAnnouncement(` in a
notifier, view model, bloc, cubit, controller or state file.
**Why:** announcements need localised text and a `TextDirection` from the
view. Logic that announces can't be localised properly or tested without a
widget tree, and it tends to grow a `BuildContext` (ARCH-102).
**Fix:** emit a status or effect and announce from the view's listener. The
`note` gives the profile's way (`placement-by-architecture.md`).
**False positives:** none known.

### Suppression

`// a11y-ignore: A11Y-003 <reason>` on the reported line, the line above, or
any line inside the reported call; `// a11y-ignore-file: A11Y-004 <reason>`
anywhere in the file. Several IDs may be listed with commas. Suppressed hits
go to `suppressed` in the JSON with their reason, and the text report ends
with `suppressed: N (see --json)`.

## 3. Reading-level findings (A11Y-<slug>)

These need judgement, so they come from reading the code, not the checker:

| ID | Severity | Look for | Fix |
|---|---|---|---|
| A11Y-colour-only-meaning | Medium | status shown only by colour | add an icon, text or `Semantics(value:)` |
| A11Y-custom-control-no-role | Medium | custom switch/slider/checkbox without `toggled:`/`checked:`/`slider:` and actions | set the flags and actions, or use the Material widget |
| A11Y-focus-order | Medium | Tab or swipe order that jumps around; modals that leak focus | `FocusTraversalGroup`, `OrderedTraversalPolicy`, `BlockSemantics` |
| A11Y-no-keyboard-access | Medium | custom controls that can't be focused or activated by keyboard or switch | `FocusableActionDetector` with `ActivateIntent` |
| A11Y-async-result-silent | Medium | a result, error or completion that appears silently | live region or an announcement from the view's listener |
| A11Y-pii-announced | Medium | names, balances or health data in announcements | announce the event, not the data |
| A11Y-motion-ignored | Low | animations, parallax or auto-play ignoring `disableAnimationsOf` | zero durations or a cross-fade when it's set |
| A11Y-label-redundant | Low | "Close button" labels (the role is read anyway), labels duplicating nearby text | shorter labels, `ExcludeSemantics` on the duplicate |
| A11Y-no-focus-indicator | Low | focusable custom controls without a visible focus state | `onShowFocusHighlight` styling |
| A11Y-no-a11y-tests | Low | screens with no `meetsGuideline` or semantics assertions | `testing-accessibility.md` §1 |

## 4. Calibration

Run on the canonical sets (every `bloc/examples/*` and `riverpod/examples/*`
project, and `compass_app`) and three non-canonical apps. The hit counts are
after the fixes. TP/FP was judged by reading the code behind every high and
medium hit (for immich's 54 A11Y-001 hits, the evidence of each and a sample
of files in full).

| App (commit) | Profile | Hits by rule (severity) | TP / FP |
|---|---|---|---|
| flutter/samples `compass_app` @5541c59 | mvvm | 002 ×5 (m), 003 ×2 (l), 005 ×1 (m), 008 ×1 (m) | all TP: icon-only `InkWell`/`InkResponse` buttons with no Semantics anywhere in the app; a 40 dp logout button; `onError: Colors.red` on `error: Colors.white` is 3.68:1 |
| felangel/bloc `examples/*` @b9be1e2 | bloc | 001 ×14 (m) in 7 examples, 003 ×1 (l) | all TP: icon `FloatingActionButton`s and `IconButton`s without tooltips; an unlabelled logo |
| rrousselGit/riverpod `examples/*` @1efba1c | riverpod | 001 ×1 (m), 003 ×5 (l) | all TP after the fix; 1 FP fixed (A11Y-009, `marvel`) |
| gskinnerTeam/flutter-wonderous-app @747b945 | provider | 003 ×8 (l), 004 ×8 (m), 005 ×1 (l), 008 ×2 (m) | all TP: a `StaticTextScale` wrapper (default scale 1) pins text size around content strings; white on `accent1` (#E4935D) is 2.43:1. No A11Y-001/002: every button goes through `AppBtn(semanticLabel:)` |
| lichess-org/mobile @99e1fb7 | riverpod | 001 ×5 (m), 002 ×3 (m), 003 ×30 (l), 004 ×1 (m) ×3 (l), 005 ×3 (l), 006 ×2 (l) | all TP; the 004 medium is a deliberate iOS-style tab bar (see A11Y-004) |
| immich-app/immich `mobile` @188d64e | riverpod | 001 ×54 (m), 002 ×4 (m), 003 ×14 (l), 005 ×1 (m) ×3 (l) | all TP after the fix; 1 FP fixed (A11Y-010) |

**FP causes fixed, each with a regression fixture and a test that the related
true positive still fires:**

| Rule | Cause | Fixture |
|---|---|---|
| A11Y-009 | `ExcludeSemantics(excluding: !isFocused, child: TextField(…))` hides the field only while collapsed | `tests/fixtures/calib_riverpod_marvel` |
| A11Y-010 | two `autofocus: true` fields in the branches of a ternary; only one is built | `tests/fixtures/calib_immich` |
| A11Y-001 | precision change from flutter_todos: an `IconButton(icon: icon)` that forwards a widget parameter is judged at its call sites, so labelled call sites no longer produce a hit at the definition | `tests/fixtures/calib_bloc_todos` |

The canonical sets have zero high or medium false positives. Their low hits
(A11Y-003) are images whose meaning the code doesn't state: logos, profile
pictures and backgrounds.

## 5. What this skill doesn't check (and who does)

| Concern | Owner |
|---|---|
| hard-coded or non-localised label strings | I18N-010 (`flutter-i18n`) |
| `obscureText`, autofill hints, field values in logs | FORM-001…004 (`flutter-forms`) |
| raw colours, type and spacing outside the theme; token structure | DS-0xx (`flutter-design-system`) |
| physical left/right layout, RTL | I18N-012 |
| focus nodes created in providers | ARCH-109 |
| `BuildContext` in logic | ARCH-102 |
| the generic `UI-a11y` slug | replaced by an A11Y-0xx finding on the same file and line |
| accessibility-service and overlay abuse, secure screens | `flutter-security-audit` (if installed) |
