---
name: flutter-accessibility
description: Write and review accessible Flutter UI, placed by the app's own architecture. Covers the semantics tree (Semantics, MergeSemantics, ExcludeSemantics, semanticLabel, icon-button tooltips, live regions, SemanticsService.announce), labels from l10n, 48 dp tap targets, WCAG contrast for ColorScheme pairs, text scaling to 200 percent, focus order, keyboard and switch access, reduced motion, and screen-reader tests with meetsGuideline and TalkBack or VoiceOver. Logic exposes status and one-time effects and the view speaks them, in MVN, MVVM, Bloc, Provider or GetX. Secrets never reach the semantics tree. Includes an A11Y checker. Use it whenever you build or review a screen, icon button, custom control or theme, or someone says "accessibility", "a11y", "screen reader", "TalkBack", "VoiceOver", "contrast" or "font size". For tokens use flutter-design-system, for hard-coded strings flutter-i18n.
license: MIT
metadata:
  author: abdelrahman-abied
  version: "1.7.1"
  suite: flutter-pro-skills
---

# Flutter accessibility

> **Writing a standard feature?** If you're filling in a feature that
> `flutter-feature-scaffold` generated, its cross-cutting rules already cover
> this skill's write-time defaults (labels, tooltips, tap targets and text scale). You can stop reading here and check
> once at the end with `bash ../dart-flutter-review/scripts/review.sh <project-root> --diff HEAD --findings-only`.
> Read on when the work is about this area itself, or to fix a finding it reports.

About one user in five relies on some accessibility setting: a screen reader,
larger text, switch or keyboard access, reduced motion or higher contrast.
Flutter draws its own pixels, so the platform only knows what the app puts in
the **semantics tree**. If a control has no label there, TalkBack and VoiceOver
announce "button" and nothing else. If the app pins the text scale, low-vision
users can't read it. This skill writes UI that works for them from the start,
in the architecture the project already uses, and without leaking secrets to
assistive technology.

The core split holds in every pattern:

- **Semantics live in the view and in design-system components.** Labels,
  hints, `Semantics(button: true)`, `header: true`, `MergeSemantics`, focus
  order and tap-target sizes are presentation. Shared components (an
  `AppIconButton`, an `AppCard`) carry them once, so feature code can't forget.
- **Logic exposes facts, not words.** A notifier, view model, bloc or GetX
  controller exposes a status enum, a count or a sealed result, and emits a
  one-time effect when something should be announced. It never builds
  user-facing strings, never holds a `BuildContext`, and never calls
  `SemanticsService.announce` (A11Y-011).
- **Labels come from l10n**, like every other user-facing string. This skill
  flags a *missing* label. `flutter-i18n` (I18N-010) flags a hard-coded one.
- **Secrets stay out of the semantics tree.** A screen reader speaks what the
  tree says, and accessibility services can read it. Describe the state
  ("Code entered"), never the value (A11Y-007).

## Workflow

### 1. Detect the architecture and the component layer

Check your agent's project instructions file (`AGENTS.md`, `CLAUDE.md`,
`GEMINI.md`, `.cursor/rules/…`, `.github/copilot-instructions.md`) for a
declared pattern, a design-system package or an accessibility target (WCAG
AA, an internal checklist). A declared convention wins. Then run the checker.
It's read-only, uses only the Python standard library, and doesn't need
`pub get`:

```bash
python3 -I <skill-dir>/scripts/check_accessibility.py <project-root>                     # text report
python3 -I <skill-dir>/scripts/check_accessibility.py <project-root> --json              # schema flutter-pro-skills/accessibility@1
python3 -I <skill-dir>/scripts/check_accessibility.py <project-root> --files changed.txt # diff review
python3 -I <skill-dir>/scripts/check_accessibility.py <project-root> --profile bloc      # declared pattern wins
```

The CLI is `check_accessibility.py <project-root> [--json] [--files <list-file-or-comma-list>]
[--profile auto|mvn|mvvm|bloc|mvc|getx|provider|riverpod|setstate] [--max n]`.
It exits `0` whenever a report is produced and `2` on a usage error. It reads
the profile and file roles from the `flutter-architecture` checker
(`../flutter-architecture/scripts/arch_check.py --json`). If that sibling is
missing, it falls back to path-based detection and says so on the
`classification:` line.

```text
== ACCESSIBILITY
  profile: mvvm (arch_check, confidence high)
  classification: arch_check files[]
  scanned: 58 files, 7 icon buttons, 9 tappables, 4 images, 0 semantics widgets, 2 color schemes
  [A11Y-002] tappable-without-label (medium) x5 — A GestureDetector/InkWell/CupertinoButton wraps only an icon ...
      lib/ui/core/ui/back_button.dart:37  InkWell(... child: Icon( size: 24.0, Icons.arrow_back, ...))
```

The text report lists the **wrappers** it found: project widgets that forward
a `tooltip:` to an `IconButton`, or pin the text scale through a default
parameter. Calls to them are judged at the call site.

### 2. Place each piece by the pattern

| Piece | MVN | MVVM + Command | Bloc / Cubit | Provider | GetX |
|---|---|---|---|---|---|
| labels, hints, roles, focus order | view / DS component | view / DS component | view / DS component | view | view |
| semantic facts (status, count, selected) | sealed state / notifier fields | view-model getters, `command.running` | state fields, status enum | model fields | `Rx` fields |
| one-time announcement | sealed effect + `ref.listen` in the view | command listener in the view | `BlocListener` | listener added in `initState` | `ever()` worker set up by the view |
| reduced motion, text scale | read in the view from `MediaQuery` | same | same | same | same |
| contrast | `ColorScheme` / `ThemeExtension` in the theme (`flutter-design-system`) | same | same | same | same |

Read `references/placement-by-architecture.md` for complete code per pattern,
including announcements of async results. Read
`references/semantics-and-labels.md` before writing a custom control, an icon
button or an image. Read `references/visual-and-input.md` for tap targets,
contrast, text scale, focus, keyboard and reduced motion. Read
`references/testing-accessibility.md` to write `meetsGuideline` and semantics
tests and to run the manual TalkBack and VoiceOver pass.

### 3. Write with the checklist below, then run the checker

Read the code behind every hit before calling it `confirmed`.
`references/rules.md` lists each rule's detection and its known false
positives. Suppress a deliberate case in the code, with a reason:
`// a11y-ignore: A11Y-003 decorative flourish; the heading names the section`
(on the reported line, the line above, or anywhere inside the call), or
`// a11y-ignore-file: A11Y-004 <reason>`.

## WRITE checklist

**Semantics and labels**
1. Give every icon-only button a `tooltip:` from l10n. It becomes the semantic
   label and the long-press hint (A11Y-001). Put it in the shared
   `AppIconButton` and make the parameter required.
2. Custom tappables (`GestureDetector`, `InkWell` around an icon or image)
   need `Semantics(button: true, label: …)`. Better: use `IconButton`, which
   already has the role, focus, the 48 dp target and the ripple (A11Y-002).
3. Every image either says what it shows (`semanticLabel:`) or is marked
   decorative (`excludeFromSemantics: true`). Decide each one (A11Y-003).
4. Group what reads as one item: `MergeSemantics` around a row's icon and
   text, `Semantics(header: true)` on section titles, `Semantics(container:
   true)` for cards, `ExcludeSemantics` only for duplicate or decorative
   content and never around a control (A11Y-009).
5. Announce async results with a live region (`Semantics(liveRegion: true)`)
   or `SemanticsService.announce`, called from the view's listener with
   localised text and `Directionality.of(context)` (A11Y-011).
6. Don't encode meaning in colour alone. Pair red and green with an icon,
   text or `Semantics(value:)`.

**Visual and input**
7. Keep tap targets at least 48x48 dp on Android and 44x44 pt on iOS. Don't
   squeeze buttons into small `SizedBox`es, and keep
   `MaterialTapTargetSize.padded` (A11Y-005).
8. Never disable or cap text scaling app-wide: no `TextScaler.noScaling`,
   `textScaleFactor: 1.0` or clamps below 2.0 in `MaterialApp.builder`
   (A11Y-004). Fix the layouts that overflow instead.
9. Avoid fixed heights around text. Use `minHeight`, padding and `Flexible`
   so text can grow to 200 % (A11Y-006).
10. Keep text contrast at 4.5:1 or more, and 3:1 for large text, icons and
    control borders (WCAG AA). Check every `ColorScheme` on-colour pair in
    light and dark (A11Y-008).
11. Give a predictable focus order (`FocusTraversalGroup`,
    `OrderedTraversalPolicy`), a visible focus indicator, keyboard support
    for custom controls (`FocusableActionDetector`, `Shortcuts`/`Actions`),
    and at most one `autofocus` per screen (A11Y-010).
12. Respect `MediaQuery.disableAnimationsOf(context)`: skip or shorten
    non-essential motion and parallax.

**Secure by default**
13. Never put a password, PIN, OTP, token or card number in `Semantics(label:
    / value:)`, `semanticsLabel:` or an announcement (A11Y-007). Obscured
    fields already expose obscured semantics; keep it that way. FORM-001
    checks `obscureText` itself.
14. Announce no PII ("Payment to J. Smith of 420 €") on shared or
    sensitive screens. Say "Payment sent" and let the user explore the screen.
15. Accessibility services can read the whole semantics tree. Treat
    overlay and service abuse as a threat, which `flutter-security-audit`
    covers (if installed).

**Tests**
16. Add a widget test per screen with `meetsGuideline(androidTapTargetGuideline)`,
    `iOSTapTargetGuideline`, `labeledTapTargetGuideline` and
    `textContrastGuideline`, and find controls with `find.bySemanticsLabel`.
    Run the manual TalkBack and VoiceOver pass before a release
    (`references/testing-accessibility.md`).

## Reviewing

For a review, read `references/review.md`: the review checklist (every
finding ID with its severity and how to confirm it) and worked finding
examples in the suite's format. Writing code doesn't need it.

## Related skills

These assume the suite is installed as sibling folders. If your agent doesn't
auto-load skills, read the path given. If a sibling is missing, carry on and
say which check you skipped.

- **`flutter-architecture`** for detecting the pattern and where logic lives.
  Fallback: `../flutter-architecture/SKILL.md`.
- **`flutter-design-system`** for tokens, `ThemeData`, `ColorScheme` and
  shared components. Fallback: `../flutter-design-system/SKILL.md` (if it's
  not installed, keep contrast checks here and say so).
- **`flutter-ui-practices`** for widget lifecycle and general UI review.
  Fallback: `../flutter-ui-practices/references/flutter-ui.md`.
- **`flutter-i18n`** for localized labels and RTL. Fallback:
  `../flutter-i18n/SKILL.md`.
- **`flutter-forms`** for field labels, obscured fields and autofill.
  Fallback: `../flutter-forms/SKILL.md`.
- **`flutter-testing`** for widget-test structure, fakes and goldens.
  Fallback: `../flutter-testing/SKILL.md`.
- **`flutter-secure-defaults`** for secrets elsewhere, and
  **`flutter-security-audit`** (installed separately) for overlay and
  accessibility-service abuse.
- The official `flutter/agent-plugins` skills and the docs.flutter.dev
  accessibility guide, when installed or reachable, for step-by-step platform
  setup. This skill adds architecture placement, review and the checker.
- **`dart-flutter-review`** merges A11Y findings into its report.

## References

| File | Read it when |
|---|---|
| `references/review.md` | reviewing: the checklist with every ID, severity and fix, and finding examples |
| `references/semantics-and-labels.md` | labelling buttons, custom controls and images; MergeSemantics, ExcludeSemantics, headers, live regions, announcements; secrets and PII in semantics |
| `references/visual-and-input.md` | tap targets, contrast (with the WCAG formula), text scale to 200 %, focus and traversal, keyboard and switch access, reduced motion, colour-only meaning |
| `references/placement-by-architecture.md` | where semantic facts, announcements and shared components go in MVN, MVVM, Bloc/Cubit, Provider, GetX, Riverpod and setState |
| `references/testing-accessibility.md` | `meetsGuideline`, `ensureSemantics`, `find.bySemanticsLabel`, semantics matchers, and the manual TalkBack, VoiceOver, Scanner and Inspector checklist |
| `references/rules.md` | every A11Y rule: detection, why, fix, false positives, suppression; the calibration table |
