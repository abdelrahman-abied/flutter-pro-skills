# Flutter UI best practices (app code)

Sources: docs.flutter.dev *Performance best practices*, *Architecture
recommendations* (with their Strong / Recommend / Conditional priorities),
the testing docs, the `flutter_lints` set, and the Flutter framework style
guide where it applies to apps. Each item says **why**, so you can judge edge
cases and not just pattern-match.

Architecture (layers, state-management patterns, repositories, DI) lives in
the `flutter-architecture` skill. If your agent doesn't auto-load skills, read
`../flutter-architecture/SKILL.md`. This file covers what happens in and
around widgets.

## Contents
1. Lifecycle and resource ownership (most common real bugs)
2. Async and `BuildContext`
3. `build()` cost and widget structure
4. Lists, layout, painting (performance)
5. UI-side state
6. Architecture (pointer to `flutter-architecture`)
7. Theming, accessibility, i18n
8. Testing (unit and widget tests)
9. What `flutter_lints` already enforces

---

## 1. Lifecycle and resource ownership

**The rule:** whoever creates a disposable object owns it and must dispose of it.
Garbage collection does not save you. A `StreamSubscription` on a long-lived
stream keeps the whole `State` (and everything it references) alive, and an
undisposed `AnimationController` keeps ticking. The Flutter guide says
"pretend Dart has no GC" when you think about ownership.

| Created in a `State` | Released in `dispose()` with |
|---|---|
| `AnimationController`, `TextEditingController`, `ScrollController`, `PageController`, `TabController`, `FocusNode`, `ValueNotifier`/`ChangeNotifier` you own | `.dispose()` |
| `StreamSubscription` | `.cancel()` (lint `cancel_subscriptions`) |
| `StreamController` / sinks | `.close()` (lint `close_sinks`) |
| `Timer` / `Timer.periodic` | `.cancel()` |
| Listeners added with `addListener` to objects you don't own | `removeListener` with the **same** function reference |

- Call `super.dispose()` **last** in `dispose()`, and `super.initState()` **first**
  in `initState()`.
- Don't dispose of what was passed in. A controller received through the
  constructor belongs to the parent. The same goes for injected clients
  (`http.Client`, `Dio`) and repositories: whoever constructs them closes them,
  usually the DI/provider layer. A view model or notifier that a screen creates
  for itself is owned by that screen, which disposes of it (and swaps it in
  `didUpdateWidget` if its inputs change).
- Process-lifetime singletons (an app-wide event bus, a `static final instance`)
  are exempt. Their "end of life" is process exit. Don't flag them, but they
  must not be re-created per screen.
- If a disposable depends on widget config, handle `didUpdateWidget`: dispose
  the old one and create the new one.
- `TickerProviderStateMixin` vs `SingleTickerProviderStateMixin`: use the single
  variant when there is exactly one controller.
- With Riverpod or Provider, dispose of things in the provider's
  `ref.onDispose` / `dispose` callback. Use `autoDispose` for screen-scoped state.

## 2. Async and `BuildContext`

- **Never use `context` after an `await` without a mounted check.** The widget
  may have been unmounted while waiting, so `Navigator.of(context)` or
  `ScaffoldMessenger.of(context)` may throw or act on the wrong route.
  ```dart
  Future<void> _handleSave() async {
    await repository.save(draft);
    if (!context.mounted) return;          // in a State: `if (!mounted) return;`
    Navigator.of(context).pop();
  }
  ```
  The lint `use_build_context_synchronously` (flutter set) catches the direct
  cases. It misses `context` captured in a closure or passed to a helper, so
  check those by reading.
  An alternative is to read what you need *before* the await:
  `final messenger = ScaffoldMessenger.of(context);`
- **`setState` after an await** needs the same `mounted` guard.
- **Don't create futures in `build()`.**
  `FutureBuilder(future: api.fetch())` refires the request on every rebuild.
  Create the future in `initState` (or in your state layer) and store it in a field.
  The same applies to `StreamBuilder` streams.
- **Unawaited futures**: a `Future` you neither `await` nor wrap in `unawaited(...)`
  hides its errors. Enable `unawaited_futures`. In callbacks like `onPressed`, a
  call to an `async` function is fine, but the function itself must handle its errors.
- **Error surfaces**: every `async` user action needs a visible failure path
  (snackbar, error state). A `try { … } catch (_) {}` around network code is a
  silent failure. See Effective Dart's error-handling rules (the
  `dart-flutter-best-practices` skill, `../dart-flutter-best-practices/references/effective-dart.md`).
- **No synchronous slow work on the UI isolate.** Use `compute()` /
  `Isolate.run()` for heavy parsing, image work or crypto. Avoid the sync
  `dart:io` methods (`readAsStringSync`) in app code (`avoid_slow_async_io`
  covers the async-but-slow ones).

## 3. `build()` cost and widget structure

`build()` can run every frame during animations and whenever an ancestor rebuilds.

- **Keep `build()` pure and cheap.** It should have no side effects, no I/O, no
  sorting or filtering of large lists (do that in the state layer and expose the
  result), and no allocation of controllers, `TextStyle` sets or `RegExp` that
  could be fields or `static final`.
- **Prefer widget classes to helper methods** (official guidance; see "Widgets vs
  helper methods"). Use `class _Header extends StatelessWidget` rather than
  `Widget _buildHeader()`. A class gets its own `Element` and `BuildContext`, can be
  `const`, skips rebuilding when its inputs are identical, and shows up in DevTools.
  A helper method rebuilds whenever its parent rebuilds. Tiny one-off helpers
  that are always rebuilt with the parent anyway are a minor issue, not a bug.
  Report them as low severity.
- **Split by what changes.** Localise `setState` to the smallest subtree that
  changes. Don't call `setState` at the screen root for a single counter. The
  same idea applies to `Consumer`/`Selector`/`ref.watch(provider.select(...))`:
  watch the narrowest piece of state.
- **Reuse identical child instances.** Rebuild traversal stops when it meets the
  *same* child instance as the previous frame. `const` constructors give you this
  for free, and the `child:` parameter of `AnimatedBuilder`, `ValueListenableBuilder`
  and `Consumer` does the same for non-const subtrees.
  ```dart
  AnimatedBuilder(
    animation: _controller,
    child: const ExpensiveLogo(),                       // built once
    builder: (context, child) => Transform.rotate(angle: _controller.value, child: child),
  );
  ```
- **`const`** where possible. Since `flutter_lints` 5.0 the `prefer_const_*` lints
  are *off by default* because they were too noisy. Use `const` yourself, but don't
  file a finding for every missing one. Flag missing `const` only on large static
  subtrees, or if the project enables the lints.
- **Read narrowly from `InheritedWidget`s.** Use `MediaQuery.sizeOf(context)`,
  `MediaQuery.paddingOf`, `MediaQuery.viewInsetsOf`, `Theme.of(context).colorScheme`.
  `MediaQuery.of(context)` subscribes to *every* MediaQuery change (keyboard,
  text scale, …) and rebuilds on all of them.
- **Keys**: give items in reorderable or animated lists stable `ValueKey(item.id)`
  keys. Never use `UniqueKey()` in `build()`, because it forces a full remount
  every frame. Public widgets take `super.key` (`use_key_in_widget_constructors`).
- **Don't override `operator ==` on widgets.** It results in O(N²) comparisons and
  defeats compiler optimisations. Cache widget instances instead.
- **`StatelessWidget` by default.** Use `StatefulWidget` only for state that is
  truly ephemeral and local (animation, text field focus, a tab index), or for
  resources that need `dispose`.
- Put `child`/`children` **last** in widget constructor calls
  (`sort_child_properties_last`). Use `SizedBox` for whitespace, not an empty
  `Container` (`sized_box_for_whitespace`), and don't wrap a single child in a
  pointless `Container` (`avoid_unnecessary_containers`). Prefer `ColoredBox` /
  `DecoratedBox` / `Padding` when you need only one of `Container`'s jobs
  (`use_colored_box`, `use_decorated_box`).

## 4. Lists, layout, painting (performance)

Budget: build and raster each frame in ≤16 ms at 60 Hz (≤8 ms at 120 Hz).
Measure in **profile mode** with DevTools before you micro-optimise.

- **Be lazy with long lists.** Use `ListView.builder` / `.separated`,
  `GridView.builder`, `SliverList.builder`. `ListView(children: items.map(...).toList())`
  and `Column` inside a `SingleChildScrollView` build every item up front.
- **Avoid intrinsics.** `IntrinsicHeight`/`IntrinsicWidth` and
  `shrinkWrap: true` on long lists cause extra layout passes. Prefer
  slivers (`CustomScrollView`) over nesting scrollables with `shrinkWrap`.
- **Opacity and clipping are expensive** (they can trigger `saveLayer`). Use
  `AnimatedOpacity`/`FadeTransition`/`FadeInImage` for animations, not `Opacity`.
  For static translucency, draw with a semi-transparent colour. For rounded corners,
  use `borderRadius` on the decoration instead of `ClipRRect` where possible. Avoid
  clipping inside animations.
- **Images**: size them (`cacheWidth`/`cacheHeight`, or `ResizeImage`) to their
  display size. Decoding a 4000 px photo for a 64 px avatar wastes memory and time.
- **Animations**: prefer implicit animations (`AnimatedContainer`,
  `AnimatedOpacity`, `AnimatedSwitcher`, `TweenAnimationBuilder`) for simple
  A-to-B transitions. They need no controller and nothing to dispose. Reach for
  an `AnimationController` only when you need to start, stop, repeat or sync the
  animation, and then dispose of it (§1). Pass static subtrees as `child` (§3).
- **Strings in loops**: use `StringBuffer`, not `+`.
- **`sync*`/`async*` generators** have overhead. Return a `List` when the caller
  consumes everything anyway (Flutter style guide).

## 5. UI-side state

How state is held and flows between layers (sealed states vs `AsyncValue` vs
status enums, immutability, one source of truth, DI) is an architecture
decision: see the `flutter-architecture` skill
(`../flutter-architecture/references/state-management.md`). On the widget side:

- **Ephemeral vs app state.** Keep state that only one widget cares about
  (a tab index, an animation, a text field's focus) in a `StatefulWidget`. Put
  anything another screen, a test or a restart cares about in the project's
  state layer. Don't promote ephemeral state to a global provider, and don't
  hide app state in a `State` field.
- **Render state exhaustively.** `switch` over the sealed state (or
  `AsyncValue`, or the status enum) in `build()`, with no `default:` that hides
  a missing case. That way a new state variant becomes a compile error in the
  view instead of a blank screen.
  ```dart
  return switch (state) {
    ProfileLoading() => const Center(child: CircularProgressIndicator()),
    ProfileLoaded(:final user) => ProfileCard(user: user),
    ProfileFailed(:final message) => ErrorView(message: message, onRetry: onRetry),
  };
  ```
- **Don't copy state into the widget.** Copying a view model or provider value
  into a `State` field and then `setState`-ing it creates two sources of truth
  that drift. Read it where you render it.
- **Events go up, data comes down.** Widgets call the logic holder (`onPressed:
  notifier.save`, `bloc.add(CartItemAdded(item))`, `viewModel.save.execute()`).
  They don't mutate models directly.
- **One-time effects** (snackbar, dialog, navigation) belong in a listener
  (`ref.listen`, `BlocListener`, a command/`Listenable` listener), not in
  `build()` and not as a `showSnackbar` boolean in the state.
- **Watch narrowly** (`select`, `Selector`, `BlocSelector`, `context.select`) so
  a widget rebuilds only for the field it shows (§3).

## 6. Architecture (pointer)

Patterns, layers and their rules are covered by the `flutter-architecture`
skill (`../flutter-architecture/SKILL.md`), which detects the project's pattern
and judges code by that pattern's own rules. For MVN, its author's spec is the
`mvn` skill, if installed. The UI-relevant core:

- **No logic in widgets** (Strong in the Flutter guide). A view may contain only
  simple show/hide conditions on a flag, animation logic, layout logic from
  device info, and simple routing. Everything else goes to the view model,
  notifier, bloc or controller the project uses.
- **No I/O in widgets.** A widget never constructs an HTTP client, opens a
  database or parses JSON. It receives its logic holder through the project's
  DI (constructor, provider, `BlocProvider`).
- **Respect the project's architecture.** Don't recommend switching state
  solutions in a UI review.

## 7. Theming, accessibility, i18n

- Read colours and text styles from `Theme.of(context)` (`colorScheme`,
  `textTheme`). Hard-coded `Color(0xFF…)` or `TextStyle(fontSize: 14)` in feature
  widgets drift from the design system and break dark mode. Use 8-digit hex
  (`use_full_hex_values_for_flutter_colors`).
- **Accessibility**: tappable icons need a `tooltip` or `Semantics(label:)`. Tap
  targets should be ≥48×48 dp. Don't encode meaning in colour alone. Make sure
  layouts survive a 200 % text scale (avoid fixed heights around text).
- **i18n**: no user-facing string literals in widgets if the app is localised.
  Use `AppLocalizations.of(context)`/gen-l10n. Use `EdgeInsetsDirectional` /
  `AlignmentDirectional` so layouts work right-to-left (important for Arabic and
  Hebrew markets).
- `print` is banned in app code (`avoid_print`). Use `debugPrint` / `dart:developer`
  `log` / the project's logger, and log only actionable messages.

## 8. Testing

- **Unit test** every repository, service and view model method (Strong).
  **Widget test** views, especially routing and DI wiring.
- **Prefer fakes to mocks** (Strong). A fake repository with in-memory data tests
  behaviour, while mocks test call sequences and break on refactors. Writing
  code that is easy to fake pushes you towards small classes with clear inputs
  and outputs.
- Keep each test self-contained, with no order dependence. Prefer more, smaller
  test files over long ones.
- Avoid `@visibleForTesting` as a design crutch. If a test needs it, the unit is
  probably too big.
- **Widget tests**: wrap the widget in what it needs from above (`MaterialApp`
  with the app's theme and localization delegates, a `ProviderScope` with
  overrides, `BlocProvider.value` with a fake bloc). Inject fakes through the
  same DI the app uses, never by reaching into globals.
- **Find by meaning**: prefer `find.text`, `find.byType`, `find.bySemanticsLabel`
  or a `ValueKey` you added for the test over `find.byWidgetPredicate` on
  internals. Semantics finders double as an accessibility check.
- **`pump` vs `pumpAndSettle`**: `pumpAndSettle` waits until no frames are
  scheduled, so it times out on endless animations (`CircularProgressIndicator`,
  a repeating controller). Use `pump()` or `pump(duration)` there.
- **Layout under stress**: test narrow sizes and large text scales
  (`tester.view.physicalSize`, `MediaQuery` with a larger `textScaler`), and
  reset them with `addTearDown`.

## 9. What `flutter_lints` already enforces

It includes `package:lints/recommended.yaml` (and so `core`) plus:
`avoid_print`, `avoid_unnecessary_containers`, `avoid_web_libraries_in_flutter`,
`no_logic_in_create_state`, `prefer_const_constructors_in_immutables`,
`sized_box_for_whitespace`, `sort_child_properties_last`,
`use_build_context_synchronously`, `use_full_hex_values_for_flutter_colors`,
`use_key_in_widget_constructors`.

The set does **not** check disposal, `MediaQuery.of`, helper-method widgets,
futures in `build`, logic in widgets, lazy lists, keys, theming or accessibility.
Those are judgment items. The review script of the `dart-flutter-review` skill
(`../dart-flutter-review/scripts/review.sh`) greps for several of them as
candidates. If that skill isn't installed, check them by reading.
