# flutter-design-system: review checklist and finding examples

Moved out of `SKILL.md` so writing code doesn't load it: read this file
when you review code in this area, or when `dart-flutter-review` sends
you here. Paths are relative to the skill folder.

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
