---
name: flutter-design-system
description: Build and review a Flutter design system, clean by default and placed by the app's architecture. Tokens (ColorScheme.fromSeed, TextTheme, spacing, radius, motion), Material 3 ThemeData, component themes, ThemeExtension done right (immutable, lerp, registered in every theme), shared components over Material widgets, dark mode, high contrast, ThemeMode from settings, golden tests and bundled fonts over google_fonts fetching. Logic and state expose semantic values like Severity.warning, never Color or TextStyle, in MVN, MVVM, Bloc, Riverpod, Provider or GetX. A DS checker finds raw colours and font sizes, magic spacing, unregistered extensions and missing dark themes. Use it whenever code touches ThemeData, colours, text styles, spacing or shared components, or someone says "design system", "tokens", "dark mode" or "hardcoded color". For contrast and text scale load flutter-accessibility.
license: MIT
metadata:
  author: abdelrahman-abied
  version: "1.4.0"
  suite: flutter-pro-skills
---

# Flutter design system

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

## REVIEW checklist

Script rules (`DS-0xx`, full detail and false positives in `references/rules.md`):

| ID | Name | Default severity | What it catches |
|---|---|---|---|
| DS-001 | raw-color-in-widget | Low (Info without a design system, or black/white only) | `Color(0x…)`, `Color.fromARGB/fromRGBO`, `Colors.<name>` in a widget outside theme/token code |
| DS-002 | raw-text-style-in-widget | Low (Info without a design system) | `TextStyle(fontSize: 18)` / `GoogleFonts.x(fontSize: 18)` in a widget |
| DS-003 | magic-spacing | Low, only when the project has a spacing scale | literal `EdgeInsets`, gap `SizedBox`, `Gap(n)`, `spacing:` values |
| DS-004 | magic-radius | Low, only when the project has a radius scale | `BorderRadius.circular(10)`, `Radius.circular(10)` (pills ≥ 99 skipped) |
| DS-005 | theme-extension-not-registered | High with `extension<T>()!`, Medium otherwise | an extension in the light theme but not the dark one (or the reverse), or read with `!` and registered nowhere |
| DS-006 | theme-extension-lerp-missing | Low | an extension whose `lerp` never interpolates (`return this`) |
| DS-007 | theme-extension-mutable | Medium | a non-final field in a `ThemeExtension` |
| DS-008 | theme-mode-without-dark-theme | Medium | `MaterialApp`/`GetMaterialApp` with `themeMode:` and no `darkTheme:` |
| DS-009 | brightness-branch-in-widget | Low (Medium for platform brightness with a user ThemeMode) | branching on `Theme.of(context).brightness`, `platformBrightnessOf`, `Get.isDarkMode` in a widget |
| DS-010 | fresh-theme-in-subtree | Medium | `Theme(data: ThemeData(...))` that discards the app theme below it |
| DS-011 | visual-token-in-logic | Medium (Low under getx, setstate, mvc) | `Color`/`TextStyle`/`IconData` fields or getters in a notifier, view model, bloc, cubit, controller or state |
| DS-012 | google-fonts-runtime-fetching | Low, once per project | `google_fonts` used without `allowRuntimeFetching = false` |

Reading-level findings (`DS-<slug>`; the checker can't see these):

| ID | Severity | Look for |
|---|---|---|
| DS-remote-theme-unvalidated | High | server or user theme data applied without typed parsing and validation |
| DS-sensitive-value-unmasked | Medium | full card numbers, IBANs or balances in ad-hoc `Text`, tooltips or semantics labels |
| DS-no-component-layer | Medium | screens styling raw `ElevatedButton`/`TextField`/`Card` everywhere, with no shared components or component themes |
| DS-component-takes-colors | Low | app components with `Color`/`TextStyle` parameters instead of semantic variants |
| DS-theme-built-per-build | Low | `ThemeData`/`ColorScheme.fromSeed` rebuilt on every rebuild of a busy app root |
| DS-missing-high-contrast | Low | no `highContrastTheme` in an accessibility-sensitive app |
| DS-material2-leftovers / DS-no-component-goldens / DS-platform-check-in-feature | Low | see `references/rules.md` §3 |

**Don't report here (cross-reference instead):**
- contrast ratios, text scale, tap targets, semantics: `flutter-accessibility`
  (A11Y-0xx). DS owns the token structure, A11Y owns whether the values are
  accessible.
- `EdgeInsets.only(left:)` vs directional: I18N-012. DS judges only the number.
- a logic file importing `material.dart` for widgets: ARCH-009. A domain file
  importing Flutter: ARCH-003. A core component importing a feature: ARCH-013.
- the review heuristic `hardcoded-color` and the slug `UI-hardcoded-style`:
  when this checker ran, DS-001/DS-002 replace them for the same file and line.

**When not to flag:**
- colours inside theme files, token classes, ThemeExtensions, painters and
  illustrations: that's where they belong.
- an enum → `Color` mapping function in the presentation layer: that's the
  recommended shape (bloclibrary's weather example). Suggest mapping to
  `colorScheme` roles instead of `Colors.*` only if the app has them.
- literal padding in a project with no spacing scale. Suggest creating the
  scale once (Info), and don't file a finding per screen.
- `CupertinoColors.*` dynamic colours, and a `CupertinoApp` without a dark
  theme.
- the app root reading `platformBrightness` to resolve `ThemeMode.system`.

## Finding examples

Use the suite's finding format (`dart-flutter-review` merges them):

```markdown
### [HIGH] Dark mode crashes: AppColors isn't registered in the dark theme
- id: DS-005
- where: lib/core/design_system/theme/app_theme.dart:14, lib/core/design_system/theme/app_colors.dart:22
- evidence: `dark = ThemeData(... extensions: const [StatusColors.dark])` has no AppColors; `context.appColors` does `extension<AppColors>()!`
- rule: register every ThemeExtension in every theme (flutter-design-system › tokens-and-theming.md §6)
- why: the first widget that reads context.appColors in dark mode throws a null-check error; light-mode tests never hit it
- fix: |
    static final dark = ThemeData(..., extensions: const [AppColors.dark, StatusColors.dark]);
    // and a test: expect(AppTheme.dark.extension<AppColors>(), isNotNull);
- confidence: confirmed

### [MEDIUM] Order status colour is held in the bloc state
- id: DS-011
- where: lib/features/orders/presentation/bloc/order_state.dart:7
- evidence: `final Color statusColor;` set by the bloc from `Colors.orange`
- rule: Bloc: the state carries a status enum; BlocBuilder maps it to theme roles (components-and-placement.md §4)
- why: dark mode and high contrast get the light-theme orange, and bloc tests assert a hex value instead of the status
- fix: |
    enum OrderHealth { onTrack, delayed, failed }
    final OrderHealth health;   // in the state
    // view: color: switch (state.health) { OrderHealth.delayed => context.appColors.warning, ... }
- confidence: confirmed
```

Open the report with one line naming the profile and what the design system
already has (`mvn, ColorScheme.fromSeed + AppColors extension, AppSpacing
scale, no radius scale`). Report a project-wide pattern (no `darkTheme`
anywhere, every screen styling raw buttons) **once**, with a few locations.

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
| `references/tokens-and-theming.md` | creating or changing colour schemes, the text theme, scales, ThemeData and component themes, a ThemeExtension, dark and high-contrast themes, Cupertino theming, fonts, or a remote theme |
| `references/components-and-placement.md` | building the design-system layer and app components, deciding where tokens, ThemeMode and semantic enums live per pattern, masked components, golden tests, migrating an app with raw styles |
| `references/rules.md` | every DS rule: detection, why, bad/good code, profile notes, false positives, suppression; the reading-level slugs; ownership; the calibration table |
