# Rebuild scope by architecture

A rebuild is cheap until it isn't: the cost is the size of the subtree that
rebuilds times how often. Every state solution has a way to subscribe to
*one value* and to keep static subtrees out of the rebuild. Use the one the
project already uses; don't add a second state library to save a rebuild.

Measure first (`diagnosing-jank.md`): turn on rebuild counts in DevTools,
interact, and fix the widgets whose counts climb with every frame or every
keystroke.

## Contents

1. The framework rules every pattern shares
2. MVN and Riverpod
3. Bloc and Cubit
4. MVVM (ChangeNotifier view models, Command)
5. Provider
6. GetX
7. setState
8. `const`, `child:` and `RepaintBoundary`

## 1. Shared rules

- **The rebuild stops at an identical instance.** If a parent rebuilds and a
  child widget is the *same object* as last frame, Flutter skips it. `const`
  constructors and the `child:` parameter of builders give you that.
- **Subscribe low.** Put the watch, selector or builder as deep as the value
  is used, not at the page root. A `Consumer`/`BlocBuilder`/`Obx` around one
  `Text` is better than one around the `Scaffold`.
- **Subscribe narrow.** Select the field, not the object. Equality decides
  whether a rebuild happens, so selected values need a sane `==` (records,
  primitives, `freezed`/`equatable` classes, or immutable collections).
- **Don't fix rebuilds by caching widgets in fields.** Split into widget
  classes instead (`UI-helper-method`), so each one has its own element and
  rebuilds on its own.

## 2. MVN and Riverpod

The MVN view is a `ConsumerWidget` that watches its notifier. Scope it:

```dart
// Bad: the whole page rebuilds when any field of the state changes
final state = ref.watch(cartNotifierProvider);
return Text('${state.total}');

// Good: rebuild only when total changes
final total = ref.watch(cartNotifierProvider.select((s) => s.total));
```

- With a **sealed state**, select a derived value:
  `ref.watch(p.select((s) => s is CartLoaded ? s.items.length : 0))`.
- With **AsyncValue**, select through it:
  `ref.watch(p.select((a) => a.valueOrNull?.title))`. In another provider use
  `ref.watch(p.selectAsync((s) => s.title))`.
- Move watches into a small `Consumer` (or a child `ConsumerWidget`) when only
  part of the page depends on them.
- `ref.read` in callbacks, `ref.watch` in `build`, `ref.listen` for one-time
  effects. Watching in a callback or reading in build both break the scope.
- In a provider's or notifier's own `build()`, watching a whole provider is
  normal composition, and PERF-008 skips it.

## 3. Bloc and Cubit

```dart
// Rebuild one widget for one field
final status = context.select((CartBloc b) => b.state.status);

BlocSelector<CartBloc, CartState, int>(
  selector: (state) => state.items.length,
  builder: (context, count) => Badge(label: Text('$count')),
);

// Rebuild only on the transitions that change this widget
BlocBuilder<CartBloc, CartState>(
  buildWhen: (previous, current) => previous.status != current.status,
  builder: (context, state) => …,
);
```

- States should be `Equatable`/`freezed` so `buildWhen` and `select` compare
  values, not identities.
- Split a page into several small `BlocBuilder`/`BlocSelector` widgets rather
  than one at the root. Side effects stay in `BlocListener` (with
  `listenWhen`), never in a builder.
- Don't emit a new state per scroll offset or animation tick. Add an event
  on a threshold crossing (load more), and keep pure visuals in the widget.

## 4. MVVM (ChangeNotifier view models, Command)

The Flutter architecture guide's views listen with `ListenableBuilder`.

```dart
ListenableBuilder(
  listenable: viewModel.load,              // the Command, not the whole view model
  child: const _StaticHeader(),            // built once, reused every rebuild
  builder: (context, child) => Column(children: [child!, if (viewModel.load.running) const LinearProgressIndicator()]),
);
```

- Listen to the narrowest `Listenable`: a `Command`, a `ValueNotifier` field
  on the view model, or `Listenable.merge([...])` of the two that matter.
- Pass static subtrees through `child:`.
- A view model that calls `notifyListeners()` for every keystroke or tick
  rebuilds every listener. Give fast-changing values their own
  `ValueNotifier` and a `ValueListenableBuilder`.
- When the view model is provided with `provider`, `context.select` works too.

## 5. Provider

```dart
final count = context.select((CartModel m) => m.count);

Selector<CartModel, int>(
  selector: (_, m) => m.count,
  child: const CartIcon(),
  builder: (context, count, child) => Badge(label: Text('$count'), child: child),
);
```

- `context.watch<T>()` and `Provider.of<T>(context)` listen to the whole
  model. In callbacks use `context.read<T>()` (or `listen: false`).
- `Consumer<T>(builder:, child:)` at the leaf, never around the page.

## 6. GetX

- One `Obx` per reactive leaf. An `Obx` wrapping a screen rebuilds the screen
  whenever any observable it reads changes.
- Read `.value` inside the `Obx` closure that needs it. Reading it outside
  doesn't subscribe at all.
- `GetBuilder` with `id:` and `update(['id'])` for controllers that aren't
  reactive. Avoid a bare `update()` that rebuilds every `GetBuilder`.
- Workers (`ever`, `debounce`) for side effects, not `Obx`.

## 7. setState

- Push the changing state down into the smallest `StatefulWidget`. A
  `setState` in the page's `State` for one counter rebuilds the page.
- For values that change per frame (scroll offset, drag position), use a
  `ValueNotifier` and `ValueListenableBuilder`, or `ListenableBuilder` on the
  controller itself (PERF-009).
- Call `setState` only when the value actually changed (derived booleans,
  threshold crossings).

## 8. `const`, `child:` and `RepaintBoundary`

- **`const`.** Use it on static subtrees. `flutter_lints` no longer enables
  the `prefer_const_*` lints, so don't file a finding per missing `const`;
  flag a large static subtree that rebuilds per frame.
- **`child:` on builders.** `AnimatedBuilder`, `ListenableBuilder`,
  `ValueListenableBuilder`, `Consumer`, `Selector` and `TweenAnimationBuilder`
  all take a `child` that's built once.
- **`RepaintBoundary`** isolates *painting*, not building. Read
  `lists-images-painting.md` §4 before adding one.
