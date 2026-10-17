# DS rules: what the checker reports, and why

## Contents

1. How the checker reads a project
2. DS-001 … DS-012
3. Reading-level findings (DS-<slug>)
4. What this skill deliberately doesn't check (and who does)
5. Calibration

`scripts/check_design_system.py` is static and read-only. It needs only the
Python standard library and no `pub get`. Every hit is a candidate: read the
code before you call a finding `confirmed`.

Suppress a hit with `// ds-ignore: DS-0xx <reason>` on the reported line or
the line above, or `// ds-ignore-file: DS-0xx <reason>` anywhere in the file.
Always give the reason. It's kept in the JSON `suppressed` list.

## 1. How the checker reads a project

**Scope.** It reads `lib/**/*.dart`, skips generated files (`*.g.dart`,
`*.freezed.dart`, `*.tailor.dart`, l10n output, "GENERATED CODE" headers) and
the `barrel`/`di` roles from arch_check. Profile and roles come from
`../flutter-architecture/scripts/arch_check.py --json` (`files[]`), or from a
path-based fallback that the `classification:` line names.

**Widget files** are files with the `view`/`widget` role, or that declare a
Widget or `State` subclass. The literal rules (DS-001…004, DS-009) only look
at widget files. Logic and state files belong to DS-011, and plain models
aren't widgets.

**Theme and token files are exempt from the literal rules.** That covers:
- a path containing `theme`, `color`/`colour`, `palette`, `style`, `token`,
  `typograph`, `dimens` or `spacing` (the same path test as the review
  heuristic `hardcoded-color`, plus a few more words);
- inside a token class, one whose name ends in `Colors`, `Palette`, `Tokens`,
  `Theme(s)`, `Style(s)`, `Typography`, `Spacing`, `Dimens`, `Insets`,
  `Radii`, `Corners`, `Shapes`, `Brand`, `Gaps`, `Elevation(s)`,
  `Duration(s)`, `Motion` or `Sizes`;
- inside any `ThemeExtension` subclass, and inside `CustomPainter`,
  `CustomClipper` and `ShapeBorder` classes (painting geometry);
- inside a `ThemeData(`, `ColorScheme(`, `TextTheme(`, `CupertinoThemeData(` or
  `*Theme(Data)(` call, and inside the `theme:`/`darkTheme:`/`highContrast*:`
  arguments of `MaterialApp`, `GetMaterialApp` and `CupertinoApp`;
- palette definitions outside functions: `static const red = Color(...)`,
  `const _caption = TextStyle(...)`, top-level `final x = GoogleFonts.y(...)`;
- semantic mappings: the body of a function or getter that returns `Color`,
  `MaterialColor` or a gradient (`Color get toColor => switch (...)`);
- files under `illustration`/`artwork`/`painters/` folders or named
  `*_painter.dart`.

**Design system present.** DS-001/002 are graded **info** when the project
has no design system yet: no `ThemeExtension`, no token class, no spacing
scale, no theme file, and no `ThemeData` beyond a seed colour. Tiny samples
then get observations, not defects.

**Scales.** A *spacing scale* is a class with at least three distinct numeric
steps between 0 and 64 whose name (or whose field names) says spacing, gap,
inset, padding, margin, dimen, gutter or layout, or that uses t-shirt names
(`xs`, `sm`, `md`, `lg`, …). A ThemeExtension with three or more `double`
fields named like that also counts, and so do three or more public top-level
`k…Spacing`/`k…Padding` constants in a non-widget file. A *radius scale* is the
same, with radius, radii, corner, rounded or shape names. Classes about
durations, elevation, opacity, fonts, icons, borders, strokes, widths or
breakpoints are never scales. The text report prints the scales it found
(`scales: spacing AppSpacing (...); radius AppRadius (...)`).

**One finding per file.** The literal rules report the first hit in each file,
with `(+N more in this file)`. Fix them all at once.

## 2. Rules

### DS-001 raw-color-in-widget

**Low** (info without a design system, or when the file's only literals are
black or white) · all profiles

**Detects:** `Color(0x…)`, `Color.fromARGB/fromRGBO/from(…)` with literal
arguments, and `Colors.<name>` (including `.shadeN` and `[N]`) in a widget
file outside the exempt places above.
**Not reported:** `Colors.transparent`, `Color(0x00……)`, `CupertinoColors.*`
(dynamic, brightness-aware), black/white inside `Shadow`/`BoxShadow` or
`shadowColor`/`barrierColor`/`scrimColor`, the `color:` of a call that also
sets `colorBlendMode` (an image tint), a fallback after a nullable extension
read (`extension<T>()?.x ?? Colors.white`), and `fromARGB`/`fromRGBO` computed
from variables (colour maths).
**Why:** a literal ignores dark mode, high contrast and the next rebrand. It
is also the most common reason a dark theme "mostly works".

```dart
// BAD
Container(color: Colors.grey[200], child: Text('Empty', style: TextStyle(color: Color(0xFF757575))));
// GOOD
final scheme = Theme.of(context).colorScheme;
Container(color: scheme.surfaceContainerHighest,
    child: Text('Empty', style: TextStyle(color: scheme.onSurfaceVariant)));
```

**Profile notes:** the same everywhere. Under GetX, read `context.theme`
roles rather than `Get.isDarkMode ? a : b`.
**False positives:** brand colours fixed by contract (a partner's logo
colour), and data-driven colours (a user-chosen label colour). Suppress them
with a reason, or move them into the palette as named tokens.

### DS-002 raw-text-style-in-widget

**Low** (info without a design system) · all profiles

**Detects:** `TextStyle(…)` or `GoogleFonts.<family>(…)` with a numeric
literal `fontSize:` in a widget file, outside the exempt places.
**Not reported:** a `Text` whose literal string has no letters or digits (an
emoji or glyph sized like an icon), and named style constants defined
outside functions.
**Why:** sizes drift from the type ramp, and a later change to `textTheme`
doesn't reach these screens.

```dart
// BAD
Text(title, style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w600));
// GOOD
Text(title, style: Theme.of(context).textTheme.titleMedium);
```

**False positives:** display numerals (a clock, a counter) sized to a layout.
Suppress them, or add a `displayClock` style to the theme.

### DS-003 magic-spacing

**Low** · all profiles · **only when the project has a spacing scale**

**Detects:** literal numbers above 2 in `EdgeInsets(Directional).all /
symmetric / only / fromLTRB / fromSTEB`, a gap `SizedBox` (exactly one of
`width`/`height`, no `child`), `Gap(n)`/`SliverGap(n)`, and literal
`spacing:`/`runSpacing:`/`mainAxisSpacing:`/`crossAxisSpacing:`.
**Why:** the project already decided its steps. A literal `13` is either an
off-scale value or a copy of a token that will not follow the next change.

```dart
// BAD
const Padding(padding: EdgeInsets.all(13), child: ...);
const SizedBox(height: 17);
// GOOD
const Padding(padding: EdgeInsets.all(AppSpacing.md), child: ...);
const SizedBox(height: AppSpacing.md);
```

**Not this rule:** `EdgeInsets.only(left:)` vs `EdgeInsetsDirectional` is
I18N-012. DS-003 judges only the number.
**False positives:** sizes that aren't spacing (a fixed 200 px header gap in
a sliver, an image placeholder). Suppress them, or name them as component
tokens.

### DS-004 magic-radius

**Low** · all profiles · **only when the project has a radius scale**

**Detects:** `BorderRadius.circular(n)`, `BorderRadiusDirectional.circular(n)`
and `Radius.circular(n)` with a literal between 0 and 99 in a widget file.
**Not reported:** 0, and 99 or more (the "pill" idiom; prefer
`StadiumBorder()`).

```dart
// BAD
ClipRRect(borderRadius: BorderRadius.circular(10), child: image);
// GOOD
ClipRRect(borderRadius: BorderRadius.circular(AppRadius.md), child: image);
```

### DS-005 theme-extension-not-registered

**High** when the extension is read with `extension<T>()!`, **Medium**
otherwise · all profiles

**Detects:**
- a `ThemeExtension` that is in a light `ThemeData`'s `extensions:` but in no
  dark one (or the reverse), when the project defines both. It's reported at
  the theme that lacks it;
- an extension read with `!` that no `ThemeData` registers at all.

Brightness comes from `ThemeData.light()/dark()`, `brightness:`, the colour
scheme's brightness, or the name of the variable or function that builds it
(`darkTheme`, `buildDark…`). A theme built from a `brightness` parameter
counts as both.
**Skipped:** when any `extensions:` list can't be resolved statically (a
variable, a spread, `palette.harmonized(...)`), when the extension is added
through `copyWith(extensions:)` with unknown brightness, and for local
`Theme`/`AnimatedTheme` overrides. The checker stays silent rather than guess.
**Why:** `Theme.of(context).extension<T>()` returns `null` in the theme that
lacks it. With `!` that's a crash the first time someone opens the app in
dark mode, a path that tests in light mode never run.

```dart
// BAD
static final light = ThemeData(extensions: const [AppColors.light]);
static final dark = ThemeData(brightness: Brightness.dark);       // AppColors missing
// GOOD
static final dark = ThemeData(brightness: Brightness.dark, extensions: const [AppColors.dark]);
```

**Fix:** register it in every theme, and add the one-line test from
`components-and-placement.md` §6.

### DS-006 theme-extension-lerp-missing

**Low** · all profiles

**Detects:** a `ThemeExtension` with instance fields whose `lerp` body calls
no `lerp` at all (`Color.lerp`, `lerpDouble`, `TextStyle.lerp`, `X.lerp`). A
plain `return this;` is the usual shape.
**Why:** `MaterialApp` animates theme changes through `ThemeData.lerp`. An
extension that doesn't interpolate snaps from the old values to the new ones
at the end of the animation, out of step with every Material colour.

```dart
// BAD
@override
StatusColors lerp(ThemeExtension<StatusColors>? other, double t) => this;
// GOOD
@override
StatusColors lerp(ThemeExtension<StatusColors>? other, double t) {
  if (other is! StatusColors) return this;
  return StatusColors(warning: Color.lerp(warning, other.warning, t)!);
}
```

Fields declared in a Dart primary constructor (`class const X(final Color a)`)
count as instance fields.

### DS-007 theme-extension-mutable

**Medium** · all profiles

**Detects:** a non-`final`, non-`const` instance field in a `ThemeExtension`
(or a `var` primary-constructor field).
**Why:** theme objects are shared by every widget below the `Theme`, and
they're compared by value to decide what rebuilds. Mutating a field changes
colours without a rebuild, and `lerp`/`copyWith` stop meaning anything.
**Fix:** `final` fields, a `const` constructor, `@immutable`, changes through
`copyWith`.

### DS-008 theme-mode-without-dark-theme

**Medium** · all profiles (`MaterialApp`, `MaterialApp.router`, `GetMaterialApp`)

**Detects:** an app widget that passes `themeMode:` (anything except
`ThemeMode.light`) and no `darkTheme:`.
**Why:** with no `darkTheme`, Flutter uses `theme` for every mode, so the
"Dark" setting the user picked does nothing.

```dart
// BAD
MaterialApp(theme: AppTheme.light, themeMode: ref.watch(themeModeProvider));
// GOOD
MaterialApp(theme: AppTheme.light, darkTheme: AppTheme.dark, themeMode: ref.watch(themeModeProvider));
```

**Profile notes** (in the finding's `note`): MVN and Riverpod
`ref.watch(themeModeProvider)`; MVVM a settings view model through
`ListenableBuilder`; Bloc `BlocBuilder<ThemeCubit, ThemeMode>`; Provider
`context.watch<SettingsModel>()`; GetX `GetMaterialApp(darkTheme: ...)` plus
`Get.changeThemeMode`.
**Not reported:** `CupertinoApp` (it has no `darkTheme`; a
`CupertinoThemeData` without `brightness` already follows the platform).

### DS-009 brightness-branch-in-widget

**Low** (**Medium** for platform brightness when the app's `themeMode` is a
user setting) · all profiles

**Detects**, in widget files: `Theme.of(context).brightness`,
`theme.brightness` and `colorScheme.brightness` when the value is compared,
switched on or used in a `?:`, directly or through a local variable;
`Get.isDarkMode`/`context.isDarkMode`; and
`MediaQuery.platformBrightnessOf(context)` / `….platformBrightness`.
**Not reported:** brightness forwarded as an argument (`ClockStyle(brightness)`,
a chart package's `brightness:`), and any file that builds the app widget,
because the app root may resolve `ThemeMode.system` itself.
**Why:** each branch is a second, unthemed palette. It ignores high contrast,
and with platform brightness it ignores the user's in-app choice entirely.

```dart
// BAD
final isDark = Theme.of(context).brightness == Brightness.dark;
return Chip(backgroundColor: isDark ? Colors.white24 : Colors.black12);
// GOOD: both values live in the theme
return Chip(backgroundColor: context.appColors.chipBackground);
```

**Profile notes:** MVN, MVVM, Bloc and GetX notes all point at a
`ThemeExtension` registered in both themes. Under GetX, prefer it to
`Get.isDarkMode` checks.

### DS-010 fresh-theme-in-subtree

**Medium** · all profiles

**Detects:** `Theme(data: ThemeData(...))` (or `.light()`/`.dark()`/`.from()`)
in a widget file whose data doesn't reference the current theme
(`Theme.of`, `context`, a `theme` variable, `copyWith`) and isn't inside an
app widget's arguments.
**Why:** a new `ThemeData` resets the colour scheme, the text theme, every
component theme and every extension for the subtree. `extension<T>()!` below
it then crashes, and the subtree looks like a different app.

```dart
// BAD
Theme(data: ThemeData(useMaterial3: true), child: promo);
// GOOD
Theme(data: Theme.of(context).copyWith(cardTheme: const CardThemeData(elevation: 0)), child: promo);
```

**False positives:** a deliberately isolated preview (a theme playground).
Suppress it with a reason. `AnimatedTheme(data: isFocused ? ThemeData.light() : ThemeData.dark())`
is not reported. It's a local inversion and rarely holds extensions.

### DS-011 visual-token-in-logic

**Medium** under mvn, mvvm, bloc, riverpod and provider; **Low** under getx,
setstate, mvc and unknown

**Detects:** an instance field or getter of type `Color`, `MaterialColor`,
`TextStyle`, `IconData`, a gradient, `BoxDecoration`, `BoxShadow` or
`ShapeBorder` (also `List<Color>`), or an untyped field initialised with
`Colors.x`/`Color(…)`/`TextStyle(…)`/`Icons.x`, in a class in a `logic` or
`state` file (notifiers, view models, blocs, cubits, controllers, states).
Enums in those files count too.
**Not reported:** static constants and methods (pure helpers), classes named
like `Theme`, `Color`, `Palette`, `Style`, `Appearance` or `Brand` (theme
controllers and user colour settings), theme files, ThemeExtensions, and
widget or painter classes.
**Why:** this is the rule ARCH-009 deliberately leaves to the design system:
ARCH-009 no longer reports a `material.dart` import that's used only for value
types, so a `Color` in a bloc state passes the import check. The colour ties
the logic to one theme, so dark mode and high contrast get the light value.
It also makes view-model and bloc tests assert hex values instead of meaning.

```dart
// BAD (bloc state)
final class OrderLoaded extends OrderState { final Color statusColor; ... }
// GOOD
final class OrderLoaded extends OrderState { final OrderHealth health; ... }
// view: BlocBuilder maps health to scheme.error / context.appColors.warning
```

**Profile notes** (in `note`): MVN the sealed state carries an enum; MVVM the
view model exposes an enum; Bloc a status enum mapped in `BlocBuilder`;
Riverpod/Provider the provider or model exposes an enum; GetX `Rx<Severity>`
mapped in `Obx`.
**Not this rule:** a domain entity importing Flutter is ARCH-003, and a logic
file importing `material.dart` for widgets is ARCH-009.

### DS-012 google-fonts-runtime-fetching

**Low** · all profiles · reported once per project

**Detects:** `google_fonts` in `pubspec.yaml`, a `GoogleFonts.<family>` call
in `lib/`, and no `GoogleFonts.config.allowRuntimeFetching = false` anywhere
in `lib/`.
**Why:** by default the package downloads fonts from `fonts.gstatic.com` at
runtime. That's a third-party request carrying the user's IP address on
first launch, the wrong font offline, and layout shift when it arrives. See
`tokens-and-theming.md` §9.
**Fix:** bundle the font files as assets and set
`GoogleFonts.config.allowRuntimeFetching = false;` in `main()`.
**False positives:** apps that set the flag in a file outside `lib/` (a
`bootstrap` package). Suppress the finding with a reason.

## 3. Reading-level findings (DS-<slug>)

The checker can't see these. Report them from reading the code, in the §4
finding format.

| ID | Severity | Look for |
|---|---|---|
| DS-remote-theme-unvalidated | High | a theme, palette or font URL from a server or user input applied without parsing into a typed object and validating it (`tokens-and-theming.md` §10) |
| DS-sensitive-value-unmasked | Medium | card numbers, balances or IBANs rendered by ad-hoc `Text` widgets instead of a shared masked component; full values in `semanticsLabel`, `Tooltip` or keys |
| DS-no-component-layer | Medium | feature screens styling raw `ElevatedButton`/`TextField`/`Card` with per-call `style:` everywhere, and no shared components or component themes |
| DS-component-takes-colors | Low | an app component with `Color`/`TextStyle` parameters instead of semantic variants (`AppButtonVariant.danger`) |
| DS-theme-built-per-build | Low | `ThemeData(...)`/`ColorScheme.fromSeed(...)` rebuilt in the app widget's `build()` on every rebuild of a frequently rebuilding root (cache it) |
| DS-missing-high-contrast | Low | an app that targets accessibility-sensitive users (banking, health, government) without `highContrastTheme`/`highContrastDarkTheme` |
| DS-material2-leftovers | Low | `primarySwatch`, `accentColor`, `ButtonTheme`, `useMaterial3: false` in new code |
| DS-no-component-goldens | Low | shared components without golden tests in light and dark (`components-and-placement.md` §6) |
| DS-platform-check-in-feature | Low | `Platform.isIOS ? CupertinoX : MaterialX` in feature code instead of an adaptive component |

## 4. What this skill deliberately doesn't check (and who does)

| Concern | Owner |
|---|---|
| contrast ratios, text scale, tap targets, semantics labels | `flutter-accessibility` (A11Y-0xx). DS owns the token structure, A11Y owns whether the values are accessible |
| `EdgeInsets.only(left:)`, physical vs directional layout | `flutter-i18n` I18N-012. DS ignores direction and judges only magic numbers |
| a logic file importing `material.dart` for widgets | ARCH-009; a domain file importing Flutter is ARCH-003 |
| a core component importing a feature | ARCH-013 |
| controllers, `dispose`, `const` constructors, `MediaQuery.of` | `flutter-ui-practices` and the review heuristics |
| `Opacity` widgets, rebuild cost of a theme switch | `flutter-performance` |
| storing the ThemeMode choice | `flutter-persistence` |

**Supersedes (CONTRACTS §23).** When `check_design_system.py` ran, DS-001
owns hard-coded colours. The review heuristic `hardcoded-color` keeps only its
count and points at DESIGN SYSTEM (`defer-ds`), and DS-001/DS-002 beat the
reading-level slug `UI-hardcoded-style` for the same file and line.

## 5. Calibration

Run on the canonical sets (flutter/samples `compass_app`, every
`felangel/bloc` example, every `rrousselGit/riverpod` example) and on four
non-canonical apps. Every high and medium hit was read. Hits are findings
(one per file for the literal rules), by severity: H/M/L/I.

| App | Commit | Profile | Hits | TP / FP |
|---|---|---|---|---|
| flutter/samples compass_app | flutter/samples@5541c59 | mvvm | DS-001 L2 I1, DS-002 L1, DS-009 L1, DS-012 L1 | all TP (purple gradient, `grey[200]` placeholder, `GoogleFonts.openSans(fontSize: 18)` over the theme's text theme, `switch (brightness)` beside an unused `TagChipTheme`, runtime font fetching). 0 H/M |
| felangel/bloc examples (16 projects) | felangel/bloc@b9be1e2 | bloc | firebase_login DS-001 L2, DS-012 L1; flutter_timer DS-001 L1; flutter_weather DS-012 L1; DS-001 I3 elsewhere | all TP. 0 H/M |
| rrousselGit/riverpod examples (7 projects) | rrousselGit/riverpod@1efba1c | riverpod | stackoverflow DS-001 L3, DS-002 L2; marvel/pub/todos/first_app info only | all TP (stackoverflow defines `QuestionTheme`/`TagTheme` tokens, then bypasses them). 0 H/M |
| gskinnerTeam/flutter-wonderous-app | gskinnerTeam/flutter-wonderous-app@747b945 | provider | DS-001 L3 I11, DS-003 L14, DS-004 L2 | TP after fixes (literal padding and radius beside `$styles.insets`/`corners`) |
| lichess-org/mobile | lichess-org/mobile@99e1fb7 | riverpod | DS-001 L24 I26, DS-002 L64, DS-009 L19 | TP after fixes. One M was an FP (static helper), fixed |
| immich-app/immich (mobile) | immich-app/immich@188d64e | riverpod | DS-001 L45 I24, DS-002 L36, DS-009 L1 | TP (`Colors.red[300]` for errors beside a full colour scheme) |
| immich-app/immich (mobile/packages/ui) | immich-app/immich@188d64e | setstate | DS-001 L1 I1, DS-003 L10, DS-004 L1 | TP (components use 16/20 beside `ImmichSpacing`/`ImmichRadius`) |
| simolus3/drift examples/app | simolus3/drift@c907be8 | riverpod | DS-001 I3, DS-002 I1 | info only (no design system) |

**False-positive causes fixed, each with a `calib_<app>` regression fixture
and a test that the related true positive still fires:**

| Fixture | Cause | Fix |
|---|---|---|
| `calib_compass_dimens` | compass `Dimens` subclasses (100/64/128 screen sizes) read as a spacing scale, so every `SizedBox(width: 10)` became DS-003 | a scale needs three distinct steps between 0 and 64 |
| `calib_compass_ext_fallback` | `extension<TagChipTheme>()?.onChipColor ?? Colors.white` | a fallback after a nullable extension read is exempt |
| `calib_compass_scrim` | black text shadows and image darkening (`color:` + `colorBlendMode:`) | shadows, scrims and image tints exempt; lone black/white graded info |
| `calib_bloc_weather` | `Color get toColor => switch (condition)` (the recommended enum → colour mapping), `Color.fromARGB(alpha, red + …)` colour maths, `Text('🏙️', style: TextStyle(fontSize: 64))` | mapping bodies, computed colours and glyph-only text are exempt |
| `calib_bloc_shopping_model` | `Colors.primaries[...]` in a plain `Item` model in `presentation/` | the literal rules need a widget file |
| `calib_marvel_local_theme` | `AnimatedTheme(data: isFocused ? ThemeData.light() : ThemeData.dark())` counted as the app's dark theme, so a light-only extension would be DS-005 high | local `Theme`/`AnimatedTheme` data isn't an app theme |
| `calib_wonderous` | `Color(0x00000000)`, illustration art colours, `BorderRadius.circular(99/999)` pills | transparent hex, illustration/painter code and radii ≥ 99 are exempt |
| `calib_lichess` | `static Color getFilterColor(...)` in a settings notifier file (DS-011 medium); private `k…Padding` constants in a widget file read as a scale; brightness forwarded to `ClockStyle(brightness)`; `class const X(...) extends ThemeExtension` (primary constructor) not parsed; `theme.copyWith(extensions: [...])` invisible to DS-005 | static members skipped; scales need public constants in a non-widget file; DS-009 needs a branch; the class parser handles primary constructors; `copyWith(extensions:)` makes DS-005 stay silent |
| `calib_samples_m3demo` | flutter/samples `material_3_demo` resolving `ThemeMode.system` with `platformBrightness` in the app root (DS-009 medium) | files that build the app widget are skipped |

**Known limits.** DS-005 is silent whenever extensions are assembled
dynamically, so read `ThemeData` construction by hand in white-label apps.
DS-003/004 can't tell a component's fixed size from spacing. Suppress those
with a reason.
