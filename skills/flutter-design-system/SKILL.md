---
name: flutter-design-system
description: Build and review a Flutter design system, clean by default and placed by the app's architecture. Tokens (ColorScheme.fromSeed, TextTheme, spacing, radius, motion), Material 3 ThemeData, component themes, ThemeExtension done right (immutable, lerp, registered in every theme), shared components over Material widgets, dark mode, high contrast, ThemeMode from settings, golden tests and bundled fonts over google_fonts fetching. Logic and state expose semantic values like Severity.warning, never Color or TextStyle, in MVN, MVVM, Bloc, Riverpod, Provider or GetX. A DS checker finds raw colours and font sizes, magic spacing, unregistered extensions and missing dark themes. Use it whenever code touches ThemeData, colours, text styles, spacing or shared components, or someone says "design system", "tokens", "dark mode" or "hardcoded color". For contrast and text scale load flutter-accessibility.
license: MIT
metadata:
  author: abdelrahman-abied
  version: "1.7.1"
  suite: flutter-pro-skills
---

# Flutter design system

> **Writing a standard feature?** If you're filling in a feature that
> `flutter-feature-scaffold` generated, its cross-cutting rules already cover
> this skill's write-time defaults (colours, text styles and dark mode). You can stop reading here and check
> once at the end with `bash ../dart-flutter-review/scripts/review.sh <project-root> --diff HEAD --findings-only`.
> Read on when the work is about this area itself, or to fix a finding it reports.

A design system is what lets a Flutter app get a dark theme, a high-contrast
mode or a rebrand by changing one folder instead of every screen. This skill
writes tokens, themes and components that are correct for the architecture
the project already uses, and reviews code for the drift that creeps in when
screens style raw widgets.

The core split holds in every pattern:

- **Tokens are values with names.** Colour roles come from a `ColorScheme`
  (plus a `ThemeExtension` for roles Material lacks). Type comes from a
  `TextTheme`. Spacing, radius, elevation and motion are `abstract final
  class` constants, or an extension when they vary per theme.
- **The theme is built once**, in the presentation/core layer, for light,
  dark and (ideally) high contrast, and every extension is registered in all
  of them.
- **Components wrap Material widgets** and read tokens. Feature code composes
  components and never styles raw widgets.
- **Logic and state never hold visual values.** A notifier, view model, bloc
  or controller exposes meaning (`OrderHealth.delayed`), and the view maps it
  to a token.
- **The app's own scale wins.** If the project has `AppSpacing`, a literal
  `13` is drift. If it has no scale yet, a literal is a judgement call, not a
  defect.

## Workflow

### 1. Detect the architecture and the design system

Check your agent's project instructions file (`AGENTS.md`, `CLAUDE.md`,
`GEMINI.md`, `.cursor/rules/…`, `.github/copilot-instructions.md`) for a
declared pattern, a design-system package or a token naming convention. A
declared convention wins. Then run the checker. It's read-only, uses only
the Python standard library, and doesn't need `pub get`:

```bash
python3 -I <skill-dir>/scripts/check_design_system.py <project-root>                     # text report
python3 -I <skill-dir>/scripts/check_design_system.py <project-root> --json              # schema flutter-pro-skills/design-system@1
python3 -I <skill-dir>/scripts/check_design_system.py <project-root> --files changed.txt # diff review
python3 -I <skill-dir>/scripts/check_design_system.py <project-root> --profile bloc      # declared pattern wins
```

The CLI is `check_design_system.py <project-root> [--json] [--files <list-file-or-comma-list>]
[--profile auto|mvn|mvvm|bloc|mvc|getx|provider|riverpod|setstate] [--max n]`.
It exits `0` whenever a report is produced and `2` on a usage error. It reads
the profile and file roles from the `flutter-architecture` checker
(`../flutter-architecture/scripts/arch_check.py --json`). If that sibling is
missing, it falls back to path-based detection and says so on the
`classification:` line.

```text
== DESIGN SYSTEM
  profile: mvn (arch_check, confidence high)
  classification: arch_check files[]
  scanned: 142 files, 2 themes, 1 theme extensions, design tokens: yes
  scales: spacing AppSpacing (lib/core/design_system/tokens/app_spacing.dart); radius none
  [DS-005] theme-extension-not-registered (high) x1 — A ThemeExtension is registered in one theme but not the other ...
      lib/core/design_system/theme/app_theme.dart:14  dark ThemeData without AppColors (registered in the light theme at ...)
```

Read the `scales:` and `design tokens:` lines first. They tell you what the
project already has, and therefore which tokens new code must use.

### 2. Place each piece by the pattern

| Piece | MVN | MVVM | Bloc / Cubit | Provider | Riverpod | GetX |
|---|---|---|---|---|---|---|
| tokens, ThemeData, extensions | `core/design_system/` | `ui/core/themes/` | `core/design_system/` or a package | `core/design_system/` | `core/design_system/` | `app/theme/` |
| components | `core/design_system/components/` | `ui/core/ui/` | same | same | same | `app/widgets/` |
| ThemeMode source | `ThemeModeNotifier` over a settings use case | settings view model | `ThemeCubit` (often hydrated) | `SettingsModel` | `Notifier<ThemeMode>` | `Get.changeThemeMode` + a service |
| semantic status | enum in the sealed state | enum getter on the view model | enum in the state | enum on the model | enum from the provider | `Rx<Severity>` |
| enum → token mapping | view | view | `BlocBuilder` builder | widget | widget | `Obx` builder |

Under Clean Architecture, the entity holds the domain enum and only
presentation maps it. Domain never imports Flutter (ARCH-003). Read
`references/components-and-placement.md` for complete code per pattern.

### 3. Write: tokens, theme, components

Read `references/tokens-and-theming.md` before you create or change a theme.
In short:

1. Generate colour roles with `ColorScheme.fromSeed` (or fill an explicit
   `ColorScheme` completely) for light and dark. Put extra roles (success,
   warning, chart series) in one `ThemeExtension`.
2. Define one `TextTheme` with sizes, heights and weights, and no colours.
3. Add `AppSpacing`/`AppRadius`/`AppMotion` as `abstract final class`
   constants, with small steps (4-pt or 8-pt).
4. Build `ThemeData` once, with component themes (`FilledButtonThemeData`,
   `InputDecorationTheme`, `CardThemeData`…) so components need no per-call
   style.
5. Write the extension with `final` fields, a `const` constructor,
   `copyWith` and a `lerp` that interpolates every field. Register it in
   **every** theme and expose it through one `context.appColors` getter that
   asserts in debug.
6. Pass `theme`, `darkTheme` (and `highContrastTheme`/`highContrastDarkTheme`)
   plus a `themeMode` read from settings.
7. Wrap Material widgets in app components with semantic variants
   (`AppButtonVariant.danger`), not `Color` parameters.
8. Map logic's enums to tokens in the view. Never put a `Color`, `TextStyle`
   or `IconData` in a state, notifier, view model, bloc or controller.

## WRITE checklist

1. Feature widgets read `Theme.of(context).colorScheme`, `.textTheme`,
   `context.appColors` and `AppSpacing`. They contain no `Color(0x…)`,
   `Colors.<name>` (except `transparent`), `fontSize:` literal or off-scale
   padding.
2. `Colors.black`/`white` only for shadows, scrims and text over imagery.
3. No `Theme.of(context).brightness == …` or `platformBrightnessOf` in
   widgets. Both values live in the theme.
4. Local variations use `Theme.of(context).copyWith(...)`, never a fresh
   `ThemeData(...)`.
5. Every `ThemeExtension` is immutable, lerps every field, and is registered
   in light, dark and high-contrast themes. A test asserts
   `theme.extension<T>() != null` for each theme.
6. `themeMode` always comes with `darkTheme`.
7. Fonts are bundled. With `google_fonts`, set
   `GoogleFonts.config.allowRuntimeFetching = false` in `main()`.
8. Shared components have golden tests in light and dark (and a large text
   scale).
9. Sensitive values (card numbers, balances) render through a shared masked
   component.

## Secure by default

- **Fonts.** Runtime font fetching sends the user's IP address to a third
  party on first launch and fails offline. Bundle the font files (DS-012).
- **Remote or user themes.** A white-label palette or a "custom theme" from
  a server is untrusted input. Parse it into a typed object in the data
  layer, validate every field (hex format, an allow-listed font family, sizes
  within the scale), check contrast, and fall back to the bundled theme on
  any error (DS-remote-theme-unvalidated). Never load fonts or images from
  theme-supplied URLs that aren't on an allow-list.
- **Sensitive content.** Ship `MaskedValue`/`SecretField`/privacy-shield
  components in the design system, so feature code can't render a full card
  number in a `Text`, a tooltip or a semantics label
  (DS-sensitive-value-unmasked).
- Everything else (token storage, logging, HTTPS, WebViews) is in
  `flutter-secure-defaults` (read `../flutter-secure-defaults/SKILL.md` if
  your agent doesn't auto-load skills).

## Reviewing

For a review, read `references/review.md`: the review checklist (every
finding ID with its severity and how to confirm it) and worked finding
examples in the suite's format. Writing code doesn't need it.

## Official recipes

For step-by-step theming mechanics, defer to the official sources if they're
installed or reachable: the `flutter/agent-plugins` theming and Material 3
recipes, `dart-lang/skills`, and docs.flutter.dev (Cookbook › Design › Use
themes; the Material 3 migration guide). This skill adds token structure,
per-architecture placement, the review checklist and the checker.

## Related skills

These assume the suite is installed as sibling folders. If your agent doesn't
auto-load skills, read the path given. If a sibling is missing, carry on and
say which check you skipped.

- **`flutter-architecture`** for detecting the pattern and the layer rules
  (ARCH-003/009/013). Fallback: `../flutter-architecture/SKILL.md`.
- **`flutter-accessibility`** for contrast, text scale, tap targets and
  semantics on top of these tokens. Fallback:
  `../flutter-accessibility/SKILL.md`. If it isn't installed, say that
  contrast wasn't checked.
- **`flutter-ui-practices`** for widget structure, `const`, lifecycle and
  the general theming notes. Fallback: `../flutter-ui-practices/SKILL.md`.
- **`flutter-i18n`** for directional layout (I18N-012) and RTL. Fallback:
  `../flutter-i18n/SKILL.md`.
- **`flutter-forms`** for secret fields inside a `SecretField` component.
  Fallback: `../flutter-forms/SKILL.md`.
- **`flutter-persistence`** for storing the ThemeMode setting, and
  **`flutter-performance`** for rebuild cost and `Opacity`. Fallbacks:
  `../flutter-persistence/SKILL.md`, `../flutter-performance/SKILL.md`.
- **`flutter-testing`** for golden-test setup and widget tests. Fallback:
  `../flutter-testing/SKILL.md`.
- **`flutter-secure-defaults`** for the rest of secure-by-default. Fallback:
  `../flutter-secure-defaults/SKILL.md`.
- **`dart-flutter-review`** merges DS findings into its report.

## References

| File | Read it when |
|---|---|
| `references/review.md` | reviewing: the checklist with every ID, severity and fix, and finding examples |
| `references/tokens-and-theming.md` | creating or changing colour schemes, the text theme, scales, ThemeData and component themes, a ThemeExtension, dark and high-contrast themes, Cupertino theming, fonts, or a remote theme |
| `references/components-and-placement.md` | building the design-system layer and app components, deciding where tokens, ThemeMode and semantic enums live per pattern, masked components, golden tests, migrating an app with raw styles |
| `references/rules.md` | every DS rule: detection, why, bad/good code, profile notes, false positives, suppression; the reading-level slugs; ownership; the calibration table |
