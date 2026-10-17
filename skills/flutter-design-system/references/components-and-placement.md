# Components and placement by architecture

## Contents

1. The design-system layer
2. Writing an app component
3. Where each piece lives, per pattern
4. Semantic values from logic, tokens in the view
5. Sensitive-content components
6. Golden tests for components
7. Migrating an app with raw styles

## 1. The design-system layer

Tokens and components are **presentation infrastructure**. They never import
a feature, a repository or a notifier, so any feature can use them, and they
can move into a package later without changes.

```
lib/
  core/
    design_system/
      tokens/        app_spacing.dart  app_radius.dart  app_motion.dart  (const scales)
      theme/         app_theme.dart  app_colors.dart (ThemeExtension)  app_typography.dart
      components/    app_button.dart  app_card.dart  app_text_field.dart  status_badge.dart
      design_system.dart   (barrel: export tokens, theme and components)
  features/
    orders/presentation/view/orders_view.dart   (composes AppCard, AppButton, StatusBadge)
```

- A multi-app or multi-package repo puts the same tree in
  `packages/design_system/` (pub workspace) and depends on it from the app.
  The checker scans one package's `lib/` at a time, so run it on the
  design-system package as well as on the app.
- Projects that follow the Flutter architecture guide use
  `lib/ui/core/themes/` and `lib/ui/core/ui/` for the same layers (that's what
  flutter/samples `compass_app` does). Keep the project's own folder names.
  Folder names don't matter to the checker, only what the files contain.
- The arch rule ARCH-013 (core depends on feature) already catches a
  component that imports a feature. Don't report it twice.

## 2. Writing an app component

An app component wraps one Material (or adaptive) widget, takes **semantic**
parameters, and reads every visual value from the theme:

```dart
enum AppButtonVariant { primary, secondary, danger }

class AppButton extends StatelessWidget {
  const AppButton({
    super.key,
    required this.label,
    required this.onPressed,
    this.variant = AppButtonVariant.primary,
    this.busy = false,
  });

  final String label;
  final VoidCallback? onPressed;
  final AppButtonVariant variant;
  final bool busy;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final child = busy
        ? const SizedBox.square(dimension: 20, child: CircularProgressIndicator(strokeWidth: 2))
        : Text(label);
    return switch (variant) {
      AppButtonVariant.primary => FilledButton(onPressed: busy ? null : onPressed, child: child),
      AppButtonVariant.secondary => OutlinedButton(onPressed: busy ? null : onPressed, child: child),
      AppButtonVariant.danger => FilledButton(
          style: FilledButton.styleFrom(backgroundColor: scheme.error, foregroundColor: scheme.onError),
          onPressed: busy ? null : onPressed,
          child: child,
        ),
    };
  }
}
```

- DO expose variants as enums, not `Color`/`TextStyle` parameters. A
  `color:` parameter on every component is how raw colours leak back into
  features.
- DO let the component theme (`FilledButtonThemeData`) carry shape, padding
  and minimum size. The component only picks the variant.
- PREFER composition over configuration: `AppCard(child: ...)` rather than an
  `AppCard` with twenty optional style arguments.
- Feature code composes components and **never styles raw widgets**. When a
  screen needs a new look, add a variant (or a new component) to the layer,
  then use it.
- A component may take a `BuildContext`-free style object for genuinely
  open-ended content (a chart's series colours). Pass `context.appColors.chart`
  from the view, not literals.

## 3. Where each piece lives, per pattern

Detect the pattern first: run `../flutter-architecture/scripts/arch_check.py --json`
(or read the project). The declared architecture wins.

| Piece | MVN (Riverpod codegen) | MVVM (Flutter guide) | Bloc / Cubit | Provider | Riverpod (plain) | GetX | Clean Architecture |
|---|---|---|---|---|---|---|---|
| tokens, ThemeData, ThemeExtensions | `core/design_system/` | `ui/core/themes/` | `core/design_system/` or a `theme` package | `core/design_system/` | `core/design_system/` | `app/theme/` | presentation-only (never in `domain/`) |
| components | `core/design_system/components/` | `ui/core/ui/` | same package / `core` | `core/design_system/components/` | same | `app/widgets/` | presentation |
| ThemeMode source | `ThemeModeNotifier` (`@riverpod`) over a settings use case | `SettingsViewModel` (ChangeNotifier) over a settings repository | `ThemeCubit` (often `HydratedCubit<ThemeMode>`) | `SettingsModel` (ChangeNotifier) | a `Notifier<ThemeMode>` | `Get.changeThemeMode` + a settings service | a settings use case; presentation maps the enum |
| app root reads it with | `ref.watch(themeModeProvider)` | `ListenableBuilder(listenable: settingsViewModel, ...)` | `BlocBuilder<ThemeCubit, ThemeMode>` | `context.watch<SettingsModel>().themeMode` | `ref.watch(themeModeProvider)` | `GetMaterialApp(themeMode: ...)` | as its presentation pattern |
| semantic status | sealed state field (enum) | view-model getter (enum) | state field (enum / status) | model getter (enum) | provider value (enum) | `Rx<Severity>` | domain entity field (enum) |
| enum → token mapping | view (`switch` on the enum) | view | `BlocBuilder` builder | widget | widget | `Obx` builder | presentation |

Persist the theme choice as a string or enum name through the persistence
layer (`flutter-persistence`). The logic layer holds `ThemeMode` (a plain
enum from `foundation`/`material` that ARCH-009 accepts as a value type). It
never holds a `ThemeData`.

## 4. Semantic values from logic, tokens in the view

Logic and state describe **what** is true; the view decides **how it looks**.
A `Color` in a bloc state or a view model ties the logic to one theme. It
breaks dark mode (the colour was chosen for light), it can't be unit-tested
without Flutter, and it bypasses the token layer (DS-011).

```dart
// BAD: state carries a visual value
class OrderState {
  const OrderState({required this.statusColor, required this.statusIcon});
  final Color statusColor;
  final IconData statusIcon;
}

// GOOD: state carries meaning
enum OrderHealth { onTrack, delayed, failed }

class OrderState {
  const OrderState({required this.health});
  final OrderHealth health;
}

// view
final (color, icon) = switch (state.health) {
  OrderHealth.onTrack => (scheme.primary, Icons.check_circle),
  OrderHealth.delayed => (context.appColors.warning, Icons.schedule),
  OrderHealth.failed => (scheme.error, Icons.error),
};
```

Per pattern:
- **MVN.** The sealed state (or its data class) carries the enum. The view
  switches on it. Notifiers never import `material.dart` for colours.
- **MVVM.** The view model exposes `OrderHealth get health`. The view maps it.
  A view-model test then asserts `health == OrderHealth.delayed`, not a hex
  value.
- **Bloc / Cubit.** The state has a status enum. `BlocBuilder` maps it.
  bloclibrary's own weather example maps `WeatherCondition` to a colour in an
  extension in the presentation layer, which is the right place.
- **Provider / Riverpod.** The model or provider returns the enum. The widget
  maps it.
- **GetX.** The controller exposes `Rx<OrderHealth>`. The `Obx` builder maps
  it. The checker grades DS-011 low under GetX, setState and MVC, where the
  controller and the view are less strictly separated.
- **Clean.** The entity holds the domain enum. Presentation maps it. Domain
  never imports Flutter (ARCH-003 already reports that).

User-chosen accent colours are the exception. A "pick your colour" setting is
data, so store it as an `int` (ARGB) or a palette key, expose it from the
settings logic, and build the `ColorScheme` from it in the app root. The
checker skips classes named like `Theme`/`Color`/`Palette`/`Appearance`, which
is where such settings live.

## 5. Sensitive-content components

Secure by default means the design system ships the components that handle
sensitive values, so feature code can't get them wrong:

- `MaskedValue` (card numbers, IBANs, balances): shows `•••• 4242` by default
  and reveals on an explicit tap, with a `Semantics` label that doesn't read
  the full value. Never put the unmasked value in a `Tooltip`, a
  `semanticsLabel` or a `Key`.
- `SecretField`: a wrapper around `TextField` with `obscureText`, a reveal
  toggle, `enableSuggestions: false`, `autocorrect: false` and the right
  `autofillHints` (load `flutter-forms` for FORM-001…003).
- `SensitiveScreen` / `PrivacyShield`: a wrapper that hides content when the
  app goes to the background (app-switcher snapshots). The platform-level
  screenshot protection is covered by `flutter-security-audit`.
- Don't log component props. A debug overlay that prints widget parameters
  must skip these components.

## 6. Golden tests for components

Components are the one place where pixel tests pay off: one test protects
every screen that uses the component.

```dart
void main() {
  for (final (name, theme) in [('light', AppTheme.light()), ('dark', AppTheme.dark())]) {
    testWidgets('AppButton variants ($name)', (tester) async {
      await tester.pumpWidget(MaterialApp(
        theme: theme,
        home: const Scaffold(
          body: Column(children: [
            AppButton(label: 'Primary', onPressed: null),
            AppButton(label: 'Danger', onPressed: null, variant: AppButtonVariant.danger),
            AppButton(label: 'Busy', onPressed: null, busy: true),
          ]),
        ),
      ));
      await expectLater(find.byType(Column), matchesGoldenFile('goldens/app_button_$name.png'));
    });
  }
}
```

- Test every variant in **light and dark** (and high contrast if you ship it),
  and at least one large text scale.
- Load the bundled fonts in tests (`flutter_test_config.dart` or
  `golden_toolkit`'s `loadAppFonts`). Otherwise goldens render the Ahem test
  font and miss real regressions.
- Generate goldens on one platform (CI's), because font rasterisation differs
  between macOS and Linux. Use `--update-goldens` deliberately, in its own
  commit.
- A `ThemeExtension` test: build both themes and assert that
  `theme.extension<AppColors>()` isn't null. That one line prevents DS-005.

Load `flutter-testing` for the wider test strategy (fakes, `pumpAndSettle`,
widget tests of screens).

## 7. Migrating an app with raw styles

1. Run the checker. Note the counts per rule and the `scales:` line.
2. Create the token classes and the `ThemeExtension` from the colours and
   sizes the app **already uses most**. The checker's evidence lines are an
   inventory.
3. Register the extension in every theme, and add `darkTheme` if `themeMode`
   is set (DS-005, DS-008 first; they're the bugs).
4. Move logic-held colours to enums (DS-011).
5. Replace literals screen by screen. Once a scale exists, DS-003/DS-004 start
   reporting magic numbers. Use `--files` on each PR, so reviewers only see
   the files it touched.
6. Suppress the deliberate exceptions with a reason
   (`// ds-ignore: DS-001 partner brand colour, fixed by contract`).
