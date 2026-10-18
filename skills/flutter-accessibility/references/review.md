# flutter-accessibility: review checklist and finding examples

Moved out of `SKILL.md` so writing code doesn't load it: read this file
when you review code in this area, or when `dart-flutter-review` sends
you here. Paths are relative to the skill folder.

## REVIEW checklist

Script rules (`A11Y-0xx`, full detail in `references/rules.md`):

| ID | Name | Default severity | What it catches |
|---|---|---|---|
| A11Y-001 | icon-button-without-label | Medium | `IconButton`/icon `FloatingActionButton` with no tooltip and no label around it; wrapper calls that drop a forwarded tooltip |
| A11Y-002 | tappable-without-label | Medium | `GestureDetector`/`InkWell`/`CupertinoButton` whose only child is an icon or image, with no label |
| A11Y-003 | image-without-semantics | Low | an image with neither `semanticLabel` nor `excludeFromSemantics: true` |
| A11Y-004 | text-scaling-disabled | High app-wide, Medium locally, Low for clamps between 1.3 and 2.0 | `TextScaler.noScaling`, `textScaleFactor: 1`, `TextScaler.linear(≤1.3)`, low `maxScaleFactor`, scale-pinning wrappers |
| A11Y-005 | tap-target-too-small | Medium under 44 dp, Low otherwise | a control in a box under 48 dp; `MaterialTapTargetSize.shrinkWrap` |
| A11Y-006 | fixed-height-around-text | Low | `SizedBox`/`Container` under 40 dp tall whose child is text |
| A11Y-007 | secret-in-semantics | High | a secret-looking value in `Semantics`, `semanticsLabel` or `announce` |
| A11Y-008 | low-contrast-color-scheme | Medium | a `ColorScheme` on-colour pair below 4.5:1, computed from literal colours |
| A11Y-009 | exclude-semantics-hides-control | Medium | `ExcludeSemantics` around a control, or `excludeFromSemantics: true` on a tap with no replacement |
| A11Y-010 | multiple-autofocus | Low | two `autofocus: true` widgets built together in one screen |
| A11Y-011 | announcement-in-logic | Medium | `SemanticsService.announce` in a notifier, view model, bloc or controller |

Reading-level findings (`A11Y-<slug>`; the checker can't see these):

| ID | Severity | Look for |
|---|---|---|
| A11Y-colour-only-meaning | Medium | status shown only by colour (error red, online green) |
| A11Y-custom-control-no-role | Medium | a custom switch, slider or checkbox without `Semantics(toggled:/checked:/slider:)` and actions |
| A11Y-focus-order | Medium | reading or Tab order that jumps around the screen; a modal that doesn't trap focus |
| A11Y-no-keyboard-access | Medium | custom controls that can't be focused or activated by keyboard or switch |
| A11Y-async-result-silent | Medium | a result or error that appears with no announcement or live region |
| A11Y-pii-announced | Medium | personal data spoken by an announcement on a sensitive screen |
| A11Y-motion-ignored | Low | animations or parallax that ignore `disableAnimationsOf` |
| A11Y-label-redundant | Low | labels that repeat the role ("Close button button") or duplicate nearby text |
| A11Y-no-focus-indicator | Low | a focusable custom control with no visible focus state |
| A11Y-no-a11y-tests | Low | no `meetsGuideline` or semantics assertions in the screen's widget tests |

**Don't report here (cross-reference instead):**
- hard-coded label strings: I18N-010 (`flutter-i18n`)
- `obscureText` and autofill hints on fields: FORM-001/002/003 (`flutter-forms`)
- colour, type and spacing tokens and raw `Color(0x…)` in features: DS-0xx
  (`flutter-design-system`). Contrast and text scale are judged here.
- physical left/right layout and RTL: I18N-012
- `UI-a11y` from `flutter-ui-practices`: an A11Y-0xx finding replaces it for the same file and line

**When not to flag:**
- `BackButton`, `CloseButton`, `PopupMenuButton` and `NavigationDestination`:
  they carry their own labels.
- An `IconButton` inside `Semantics(label:)`, `Tooltip`, `MergeSemantics` or a
  widget that passes a `label:`/`tooltip:` (the checker already skips these).
- `ExcludeSemantics(excluding: someCondition)` that hides a field only while
  it's collapsed.
- `MediaQuery.withNoTextScaling` on a fixed-size glyph (a chess piece, a clock
  dial) with a text alternative elsewhere. Suppress it with that reason.

## Finding examples

Use the suite's finding format (`dart-flutter-review` merges them):

```markdown
### [MEDIUM] Logout button has no label for screen readers
- id: A11Y-002
- where: lib/ui/auth/logout/widgets/logout_button.dart:51
- evidence: `InkResponse(onTap: …, child: Icon(Icons.logout))` with no Semantics or tooltip
- rule: custom tappables need a role and a label (flutter-accessibility › semantics-and-labels.md §2)
- why: TalkBack focuses an unnamed element; a blind user can't tell this signs them out
- fix: |
    Semantics(
      button: true,
      label: AppLocalizations.of(context).logout,
      child: InkResponse(onTap: viewModel.logout.execute, child: const Icon(Icons.logout)),
    )
- confidence: confirmed

### [HIGH] The one-time code is read aloud
- id: A11Y-007
- where: lib/features/auth/presentation/view/otp_view.dart:25
- evidence: `SemanticsService.announce('Your code is $otp', TextDirection.ltr)`
- rule: describe the state, never the secret (flutter-accessibility › semantics-and-labels.md §6)
- why: anyone near the phone hears the code, and accessibility services receive it as text
- fix: |
    // notifier: emit OtpEffect.codeFilled; view (ref.listen):
    SemanticsService.announce(l10n.codeFilled, Directionality.of(context));
- confidence: confirmed
```

Open the report with one line naming the profile and the component layer
(`mvvm, own AppIconButton in ui/core, no Semantics anywhere`). Report a
pattern-wide issue (no icon button in the app has a tooltip) **once**, with
a few locations and the shared-component fix.
