# Tokens and theming

## Contents

1. The token layers
2. Colour: ColorScheme first
3. Typography: TextTheme
4. Spacing, radius, elevation and motion scales
5. Material 3 ThemeData and component themes
6. ThemeExtension done right
7. Dark mode, high contrast and ThemeMode
8. Cupertino and adaptive apps
9. Fonts: bundle them, don't fetch them
10. Remote or user-supplied themes

The official guidance for theming lives at docs.flutter.dev (Cookbook ›
Design › Use themes to share colors and font styles) and in the Material 3
`ThemeData` API docs. If `flutter/agent-plugins` is installed, follow its
step-by-step theming recipe for the mechanics; this file adds the token
structure, the checker's expectations and the architecture rules.

## 1. The token layers

A design system that survives a rebrand has three layers. Each one only reads
from the layer above it.

| Layer | What it holds | Where it lives |
|---|---|---|
| Reference tokens | raw values: the brand palette, the type ramp, the 4-pt spacing steps | `lib/core/design_system/tokens/` (or a `design_system` package) as `abstract final class` constants |
| System tokens | roles: `ColorScheme.primary`, `textTheme.titleMedium`, `AppSpacing.md`, `AppColors.success` | `ThemeData` + `ThemeExtension`s, built once in `lib/core/design_system/theme/` |
| Component tokens | per-component decisions: a card's padding, a chip's radius | component themes (`CardThemeData`, `FilledButtonThemeData`) or the component widget itself |

Feature code reads **system tokens** only: `Theme.of(context).colorScheme.x`,
`Theme.of(context).textTheme.y`, `context.appColors.z`, `AppSpacing.md`. It
never reads a reference token such as `Palette.blue600`, because then a dark
theme or a rebrand has to touch every screen.

## 2. Colour: ColorScheme first

PREFER `ColorScheme.fromSeed` when the brand gives you one key colour. It
generates every Material 3 role (tonal palettes, containers, `on*` colours)
with contrast built in, for both brightnesses.

```dart
abstract final class AppTheme {
  static const _seed = Color(0xFF3355FF);

  static ThemeData light() => _build(ColorScheme.fromSeed(seedColor: _seed));
  static ThemeData dark() =>
      _build(ColorScheme.fromSeed(seedColor: _seed, brightness: Brightness.dark));

  static ThemeData _build(ColorScheme scheme) => ThemeData(
        colorScheme: scheme,
        textTheme: AppTypography.textTheme,
        extensions: [scheme.brightness == Brightness.dark ? AppColors.dark : AppColors.light],
      );
}
```

Use an explicit `ColorScheme(...)` (or `fromSeed(...).copyWith(primary: ...)`)
when the brand fixes exact values. Fill **every** role you rely on, in both
schemes. A missing `onPrimary` falls back to a generated colour that may not
meet contrast.

Colours that Material has no role for (success, warning, chart series, brand
gradients) go into a `ThemeExtension` (§6). They don't go into widget code,
and they don't go into a global `const` that ignores brightness.

DO map semantic states to roles in the view:

```dart
Color severityColor(BuildContext context, Severity s) => switch (s) {
      Severity.info => Theme.of(context).colorScheme.primary,
      Severity.warning => context.appColors.warning,
      Severity.error => Theme.of(context).colorScheme.error,
    };
```

AVOID `Colors.red` for an error. It ignores dark mode (`colorScheme.error` is
lighter on dark surfaces) and high contrast. `Colors.transparent` is fine.
`Colors.black`/`white` are fine for shadows, scrims and text over photos,
which is why the checker grades them info.

## 3. Typography: TextTheme

Define the type ramp once, as a `TextTheme`, and read it with
`Theme.of(context).textTheme.bodyMedium`. Change colour or weight with
`copyWith`. Leave the size alone, because the size is the scale.

```dart
abstract final class AppTypography {
  static const textTheme = TextTheme(
    headlineSmall: TextStyle(fontSize: 24, height: 32 / 24, fontWeight: FontWeight.w600),
    titleMedium: TextStyle(fontSize: 16, height: 24 / 16, fontWeight: FontWeight.w600),
    bodyMedium: TextStyle(fontSize: 14, height: 20 / 14),
    labelSmall: TextStyle(fontSize: 11, height: 16 / 11, letterSpacing: 0.5),
  );
}
```

Don't set `color` inside `TextTheme` styles. `ThemeData` applies `onSurface`
for you, so a hard-coded colour breaks dark mode. Text-scale behaviour
(`MediaQuery.textScalerOf`, clamping, layouts that survive 200 %) belongs to
`flutter-accessibility`.

## 4. Spacing, radius, elevation and motion scales

Use plain constants when the values don't change with the theme. They're
const, so `const EdgeInsets.all(AppSpacing.md)` still works:

```dart
abstract final class AppSpacing {
  static const double xxs = 2;
  static const double xs = 4;
  static const double sm = 8;
  static const double md = 16;
  static const double lg = 24;
  static const double xl = 32;
}

abstract final class AppRadius {
  static const double sm = 4;
  static const double md = 8;
  static const double lg = 16;
  static const BorderRadius card = BorderRadius.all(Radius.circular(md));
}

abstract final class AppMotion {
  static const Duration short = Duration(milliseconds: 150);
  static const Duration medium = Duration(milliseconds: 300);
  static const Curve standard = Curves.easeInOutCubicEmphasized;
}
```

PREFER a `ThemeExtension` instead only when the values do vary: by density,
by form factor, or between brands of a white-label app. You give up `const`,
but you gain `lerp` and per-theme values.

`abstract final class` (Dart 3) can't be instantiated, extended or
implemented. It's the idiomatic namespace for constants. A private
constructor in a plain class also works on older SDKs.

The checker (DS-003, DS-004) only reports magic numbers when your project
**has** such a scale: a class with at least three small numeric steps, named
like spacing, gap, insets or radius, or a ThemeExtension with three or more
`double` fields. Without a scale, literal padding is a judgement call, not a
finding. Pill shapes (`BorderRadius.circular(999)`) and hairlines (≤ 2) are
never reported. Prefer `StadiumBorder()` for the pill.

## 5. Material 3 ThemeData and component themes

Material 3 is the default since Flutter 3.16. Style components once, in the
theme, so every `FilledButton` and `TextField` looks the same without
per-call styling:

```dart
ThemeData(
  colorScheme: scheme,
  textTheme: AppTypography.textTheme,
  filledButtonTheme: FilledButtonThemeData(
    style: FilledButton.styleFrom(
      minimumSize: const Size.fromHeight(48),
      shape: const RoundedRectangleBorder(borderRadius: AppRadius.card),
    ),
  ),
  inputDecorationTheme: const InputDecorationTheme(
    border: OutlineInputBorder(borderRadius: AppRadius.card),
    contentPadding: EdgeInsets.symmetric(horizontal: AppSpacing.md, vertical: AppSpacing.sm),
  ),
  cardTheme: const CardThemeData(margin: EdgeInsets.zero, elevation: 0),
);
```

- DO build `ThemeData` once (a `static final` or a function called from the
  app widget), not inside a feature widget's `build()`.
- DO derive local variations from the current theme:
  `Theme(data: Theme.of(context).copyWith(...))`. A fresh `ThemeData(...)` in
  a subtree throws away the scheme, the text theme and every extension below
  it (DS-010).
- AVOID `primarySwatch` and the other Material 2 parameters in new code. They
  are deprecated or ignored under Material 3.

## 6. ThemeExtension done right

```dart
@immutable
class AppColors extends ThemeExtension<AppColors> {
  const AppColors({required this.success, required this.warning, required this.chart});

  final Color success;
  final Color warning;
  final List<Color> chart;

  static const light = AppColors(
    success: Color(0xFF2E7D32), warning: Color(0xFFB26A00),
    chart: [Color(0xFF3355FF), Color(0xFF00897B)],
  );
  static const dark = AppColors(
    success: Color(0xFF81C784), warning: Color(0xFFFFCA28),
    chart: [Color(0xFF9FB0FF), Color(0xFF4DB6AC)],
  );

  @override
  AppColors copyWith({Color? success, Color? warning, List<Color>? chart}) => AppColors(
        success: success ?? this.success,
        warning: warning ?? this.warning,
        chart: chart ?? this.chart,
      );

  @override
  AppColors lerp(ThemeExtension<AppColors>? other, double t) {
    if (other is! AppColors) return this;
    return AppColors(
      success: Color.lerp(success, other.success, t)!,
      warning: Color.lerp(warning, other.warning, t)!,
      chart: [for (var i = 0; i < chart.length; i++) Color.lerp(chart[i], other.chart[i], t)!],
    );
  }
}

extension AppColorsContext on BuildContext {
  /// Fails loudly in debug if a ThemeData forgot to register AppColors.
  AppColors get appColors {
    final colors = Theme.of(this).extension<AppColors>();
    assert(colors != null, 'AppColors is missing from ThemeData.extensions');
    return colors ?? AppColors.light;
  }
}
```

The rules, and the checker IDs that enforce them:

- **Register it in every theme** the app passes (`theme`, `darkTheme`,
  `highContrastTheme`, `highContrastDarkTheme`). `extension<T>()` returns
  `null` in a theme without it, and `!` turns that into a crash the first time
  someone opens the app in dark mode (DS-005).
- **Immutable.** Every field is `final` and the constructor is `const`.
  Theme data is shared and compared by value, so mutating a field changes
  every widget that read it, without a rebuild (DS-007).
- **`lerp` interpolates every field.** `MaterialApp` animates theme changes
  through `ThemeData.lerp`, which calls your `lerp`. Returning `this` makes
  the colours jump at the end of the animation (DS-006). Use `Color.lerp`,
  `lerpDouble`, `TextStyle.lerp`, `EdgeInsets.lerp` and `BorderRadius.lerp`.
- **`copyWith` covers every field**, so `Theme.of(context).copyWith(extensions: ...)`
  can override one value.
- **One getter** (`context.appColors`) so feature code doesn't repeat
  `Theme.of(context).extension<AppColors>()!`. The getter is the single place
  that decides how a missing registration fails.

Code generation (`theme_tailor`) is fine. The checker skips `*.tailor.dart`.

## 7. Dark mode, high contrast and ThemeMode

```dart
MaterialApp.router(
  theme: AppTheme.light(),
  darkTheme: AppTheme.dark(),
  highContrastTheme: AppTheme.lightHighContrast(),
  highContrastDarkTheme: AppTheme.darkHighContrast(),
  themeMode: themeMode, // from settings; see components-and-placement.md §3
  routerConfig: router,
);
```

- `themeMode` does nothing without `darkTheme`. Flutter falls back to `theme`
  for both, so a "Dark" setting silently shows the light theme (DS-008).
- PREFER `ThemeMode.system` as the default, and store the user's override as
  a setting (the persistence layer stores an enum name, not a `ThemeMode`
  index that might change).
- DON'T branch on brightness in widgets
  (`Theme.of(context).brightness == Brightness.dark ? a : b`). Put both
  values in the theme as a ColorScheme role or an extension field, and read
  one name (DS-009). `MediaQuery.platformBrightnessOf` in a widget is worse:
  it ignores the user's in-app choice. Only the app root, which resolves
  `ThemeMode.system`, may read it.
- High contrast: build the high-contrast themes with
  `ColorScheme.fromSeed(..., contrastLevel: 1.0)` (Flutter 3.22+) or explicit
  roles. Contrast ratios themselves are checked by `flutter-accessibility`.

## 8. Cupertino and adaptive apps

- A `MaterialApp` already adapts some widgets per platform (`Switch.adaptive`,
  scrolling physics, page transitions). For iOS-flavoured Material, set
  `cupertinoOverrideTheme: CupertinoThemeData(...)` on `ThemeData`, so the
  Cupertino widgets inside a Material app pick up your primary colour.
- A `CupertinoApp` has no `darkTheme`. A `CupertinoThemeData` without
  `brightness` follows the platform, and `CupertinoColors.systemBackground`,
  `label` and the other dynamic colours resolve per brightness by themselves.
  The checker treats `CupertinoColors.*` as semantic, not raw.
- Adaptive components (`AppSwitch` that renders `CupertinoSwitch` on iOS)
  belong in the design-system layer. Feature code shouldn't check
  `Platform.isIOS` to pick a widget.

## 9. Fonts: bundle them, don't fetch them

By default `google_fonts` downloads font files from `fonts.gstatic.com` at
runtime and caches them. In release builds that means:
- a request to a third-party server on first launch, which sends the user's
  IP address to Google (a German court has ruled that remotely loaded Google
  Fonts on a website breached the GDPR);
- the wrong font when the device is offline or the request is blocked;
- layout shift when the font arrives.

DO bundle the `.ttf` files and turn fetching off (DS-012):

```yaml
flutter:
  assets:
    - google_fonts/          # the downloaded OFL font files
```

```dart
void main() {
  GoogleFonts.config.allowRuntimeFetching = false;
  runApp(const App());
}
```

Or skip the package: declare the family under `flutter: fonts:` and use
`fontFamily: 'Inter'` in the `TextTheme`. Keep the font licence (usually OFL)
with the assets.

## 10. Remote or user-supplied themes

White-label apps and "custom theme" features load colours from a server or
from user input. Treat that as untrusted input at the data boundary:

- Parse into a typed value object (`BrandTheme.fromJson`) in the data layer,
  and validate every field: hex format, a known font family from an
  allow-list, sizes within the scale. On any error, fall back to the bundled
  theme. Never `jsonDecode` theme maps inside widgets.
- Check contrast of server-supplied colour pairs before you apply them (load
  `flutter-accessibility` for the ratio check). A bad payload shouldn't make
  the login screen unreadable.
- Never load fonts, images or shaders from URLs inside the theme payload
  unless the host is on an allow-list (see `flutter-secure-defaults` for
  HTTPS and allow-listing).
- Cache the last good theme. Don't block startup on the network.
