# Placement by architecture

Layout is a view concern in every pattern. What differs is where the shared
size classes live, where the selection that must survive a resize is kept,
and where "is this supported on this platform" is answered. Detect the
pattern first (`../flutter-architecture/scripts/arch_check.py --json`, or the
`flutter-architecture` skill) and follow the project's own conventions when
they are consistent.

## The rules that hold everywhere

- **Views decide layout.** A screen reads `LayoutBuilder` constraints or
  `MediaQuery.sizeOf(context)` and picks one pane or two, a bar or a rail.
- **Design-system components adapt internally.** A `ProductCard` that
  rearranges itself under 280 dp does it with `LayoutBuilder`; screens don't
  pass it the window width.
- **Size classes are tokens.** One enum or constants class, in the design
  system or the shared UI folder (`core/`), imported by views. Never a
  provider, bloc or controller that logic reads.
- **Logic is size-agnostic** (ADAPT-007). Notifiers, view models, blocs and
  controllers expose data: the items, the selected id, the loading and error
  state. They never hold `isTablet`, `screenWidth` or "two-pane mode", and
  never read `MediaQuery`, `View.of` or `Get.width`.
- **Capability checks live in sources.** "Does this platform support
  biometrics, badges, a system tray" is answered by a data source (kIsWeb
  first) and surfaced like any other data. Widgets don't branch on
  `Platform` to find out (ADAPT-001/002).
- **Navigation shells** (`StatefulShellRoute`, routes for the detail screen)
  are `flutter-navigation`'s; this skill only picks the bar, rail or drawer
  the shell renders.

## Where things go

| Piece | MVN | MVVM (Flutter guide) | Bloc / Cubit | Clean | Provider | GetX | Riverpod |
|---|---|---|---|---|---|---|---|
| size classes | `lib/core/presentation/layout/window_size_class.dart` or the design-system package | `lib/ui/core/ui/window_size_class.dart` | `packages/app_ui/lib/src/layout/` or `lib/app/view/` | `lib/core/presentation/layout/` | `lib/core/layout/` or the theme folder | `lib/app/core/values/` | `lib/core/layout/` (plain enum) |
| one pane or two | `presentation/view/*_view.dart` | `ui/<feature>/widgets/*_screen.dart` | `view/*_page.dart` / `*_view.dart` | presentation pages | screen widgets | `GetView` page | `ConsumerWidget` screen |
| selection that survives a resize | view `State`; or `selectedId` as data in the notifier's state | view `State`; or a view-model field with a `select` command | `selectedId` in the state, set by an event | as MVN | view `State`, or a ChangeNotifier field | an `Rx<String?>` in the controller | view `State`, or a notifier field |
| capability check | `data/sources/*_platform_source.dart` → repository → use case | `data/services/` → repository → view model | data provider → repository → bloc state | `data/datasources/` behind the domain contract | a service built at the root | a `GetxService` in the initial binding | a source provider |
| `kIsWeb` | sources, `main.dart`, DI | sources, `main.dart` | data providers, `bootstrap.dart` | data sources, DI | services, `main.dart` | services, bindings | source providers, `main.dart` |
| desktop window setup | `main.dart` / bootstrap | `main.dart` | `bootstrap.dart` | composition root | `main.dart` | `main.dart` / initial binding | `main.dart` |

## Per pattern

**MVN (Riverpod codegen notifiers + use cases).** The notifier exposes a
sealed state with the data and, if other screens need it, `selectedId`. The
view switches layout. A capability ("can this device show a tray icon")
comes through a use case from a platform source, so the notifier can be
tested with a fake. Never `ref.watch` a "screen size provider" from a
notifier.

**MVVM (Flutter architecture guide, compass_app).** The view model exposes
data and `Command`s; the screen widget in `ui/<feature>/widgets/` decides
the layout. The shared size classes sit in `ui/core/` next to the theme and
shared widgets. A list-detail selection can be a view-model field changed
by a `select` command when the detail also needs it.

**Bloc / Cubit.** States carry data, not layout. `BlocBuilder` sits inside a
`LayoutBuilder` (or reads the size class) and builds one pane or two from
the same state. A selection that survives a resize is `selectedId` in the
state, set by an event. Very Good Ventures-style apps put the size classes
in the `app_ui` package with the rest of the design system.

**Clean Architecture.** The domain never knows about screens or platforms;
"supported here" is a repository method backed by a data source. Size
classes are presentation code.

**Provider (ChangeNotifier).** The ChangeNotifier holds data. The screen
widget chooses the layout. Keep `selectedId` in the widget's `State` unless
several widgets need it.

**GetX.** Controllers expose `Rx` data; the `GetView` builds the layout.
AVOID `Get.width`, `Get.height` and `context.isTablet` in controllers
(ADAPT-007); in views prefer `LayoutBuilder` and the shared size classes
over GetX's own device helpers, so breakpoints stay in one place.
`GetPlatform` is web-safe, but tests can't override it either; prefer
`Theme.of(context).platform` for idioms.

**Riverpod (no use cases).** Providers expose data. A widget reads
`MediaQuery.sizeOf` or `LayoutBuilder` itself. A "breakpoint provider" that
needs a `BuildContext` to update is UI state in the wrong place; when you
really need one, keep it a UI-layer `InheritedWidget` or a provider only
widgets read.

**setState apps.** Same rules, smaller: the size classes in one file, the
layout in the screen, a small wrapper class for capability checks.
