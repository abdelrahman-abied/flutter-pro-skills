# State-management libraries and how they map onto the patterns

A state-management library is not an architecture. Riverpod can carry MVN,
MVVM or no pattern at all; `ChangeNotifier` backs both the Flutter team's MVVM
and hand-rolled MVC. Detect the **pattern** from roles and folders
(`detect.md`), then use this file for the library-specific rules that apply on
top.

Sources: riverpod.dev (DO/DON'T), docs.flutter.dev (state management, the
architecture case study), and the provider, GetX and Flutter SDK APIs.

## Contents

1. The mapping
2. Riverpod
3. Provider
4. ChangeNotifier, ValueNotifier and Listenable
5. setState and InheritedWidget
6. GetX
7. Others: hooks, signals, stacked, MobX, Redux
8. Mixing libraries
9. Choosing one

## 1. The mapping

| Library | Patterns it commonly carries | Profile value when no pattern naming | Library rules that apply |
|---|---|---|---|
| Riverpod (`flutter_riverpod`, codegen) | **MVN** (notifier/ folders, `*Notifier`), MVVM (`*ViewModel` + Riverpod), plain Riverpod | `riverpod` | ARCH-109, ARCH-110, `AP-riverpod-*` |
| Provider + ChangeNotifier | **Flutter MVVM** (the Compass app), hand-rolled MVC | `provider` | ARCH-109 (provider), `.value` misuse below |
| ChangeNotifier / ValueNotifier only | MVVM, MVC | `setstate`/`unknown` | dispose; read-only exposure |
| flutter_bloc | **Bloc/Cubit** | `bloc` | see `bloc.md` |
| GetX | MVC-flavoured "GetX pattern" | `getx` | ARCH-113, `AP-getx-service-locator-everywhere`; ARCH-102/104 relaxed |
| setState | none or small-app MVC | `setstate` | Flutter UI lifecycle rules (`flutter-ui-practices`) |
| mvc_pattern / fluttery_framework | MVC | `mvc` | see `mvc.md` |

Rules that change with the pattern, not the library: whether logic may call a
repository directly (MVVM, Bloc, MVC: yes; MVN: no), whether logic may depend on
other logic (MVN/Riverpod: `ref.watch` in `build()`; Bloc: no), and whether use
cases are expected.

## 2. Riverpod

riverpod.dev's DO/DON'T list (enforced in part by `riverpod_lint`):

| Rule (riverpod.dev strength) | Why | ID |
|---|---|---|
| **AVOID initializing providers in a widget.** Providers should initialize themselves | Race conditions and unexpected behaviour when a widget's `initState` calls `ref.read(p).init()`. If init depends on outside factors, do it in the action that navigates (`onPressed`) | ARCH-110 |
| **AVOID using providers for ephemeral state**: the selected item, form state, animations, anything Flutter calls a "controller" (`TextEditingController`) | Ephemeral state is route-scoped; a provider survives navigation, so the back button shows the wrong item. Use widget state or `flutter_hooks` | ARCH-109 |
| **DON'T perform side effects during the initialization of a provider.** Providers represent reads | A `FutureProvider` that POSTs a form can skip or repeat the write. Use a notifier method (or Riverpod 3 mutations) for writes | `AP-riverpod-side-effects-in-provider-build` |
| **PREFER `ref.watch/read/listen` with statically known providers** | Passing providers around as constructor arguments defeats `riverpod_lint` | `AP-riverpod-dynamic-providers` |
| **AVOID dynamically creating providers.** Providers should be top-level `final` variables | A provider created as a class field "could cause memory leaks and unexpected behaviors". Use `family` (codegen parameters) to parameterise | `AP-riverpod-dynamic-providers` |

More Riverpod idioms that matter architecturally:

- **`ref.watch` in `build()`, `ref.read` in callbacks.** `ref.watch` inside a
  notifier method or an `onPressed` subscribes at the wrong time;
  `ref.read` in `build()` misses updates.
- **`ref.listen` for one-time effects** (snackbars, navigation) in a widget's
  `build()`; never a bool flag in state (ARCH-111).
- **`AsyncValue`** (`AsyncNotifier`, `FutureProvider`) already models
  loading/error/data. A hand-rolled `isLoading` + `error` + `data` trio next to
  it is `AP-boolean-soup-state`.
- **Notifier → notifier** with `ref.watch(other)` in `build()` is sanctioned by
  Riverpod and by the MVN spec. ARCH-010 doesn't apply to `mvn` or `riverpod`.
- **`ref.mounted`** (Riverpod 3) after an `await` in a notifier method, before
  writing `state`.
- **Codegen**: `@riverpod` with `part '….g.dart';`, the generic `Ref` on
  Riverpod 3. MVN mandates it; plain Riverpod apps may use either style, but not
  both for the same job.
- **DI**: providers are the DI container; tests override them with
  `ProviderContainer(overrides: […])` / `ProviderScope(overrides: […])`. A
  `get_it` locator alongside Riverpod is a second DI mechanism (Info).

## 3. Provider

The Flutter team recommends `package:provider` for **dependency injection**,
and Compass uses it that way: `Provider`/`ChangeNotifierProvider` at the top of
the tree for services and repositories (exposed as their abstract types), view
models created in route builders with `context.read()`.

- **`create:` vs `.value`.** Use `ChangeNotifierProvider(create: …)` when the
  provider creates the object: it disposes it. `.value` is for an instance that
  already exists and is owned elsewhere. Creating a new notifier inside
  `.value` in `build()` leaks it and resets state on every rebuild.
- **`context.watch` in `build()`, `context.read` in callbacks**,
  `context.select` to rebuild on one field. `Provider.of<T>(context)` (listening)
  in `initState` throws; use `read`/`listen: false`.
- **Expose abstract types** (`Provider<BookingRepository>`), so consumers don't
  see the implementation.
- Provider *without* view-model naming is the `provider` profile. Review it as
  MVVM at reduced strength: the roles are there, only the names differ.

## 4. ChangeNotifier, ValueNotifier and Listenable

Part of the Flutter SDK, "a good solution for updating the UI when state
changes" (Flutter case study). Compass view models extend `ChangeNotifier`;
views rebuild with `ListenableBuilder`.

- Whoever creates a `ChangeNotifier` disposes it (a `ChangeNotifierProvider`
  with `create:` does this for you).
- Don't call `notifyListeners()` after `dispose()`: guard async methods.
- Expose state read-only: private fields with getters, `UnmodifiableListView`
  for lists, immutable models. A public mutable `List` lets the view change the
  model without notifying (`AP-shared-mutable-model`).
- Prefer a `Command` per action or a sealed state over per-action
  `isLoading`/`error` fields.
- `ValueNotifier<T>` + `ValueListenableBuilder` is enough for a single value.

## 5. setState and InheritedWidget

Flutter separates **ephemeral state** (one widget: the current tab, an
animation, a text field) from **app state** (shared across widgets). `setState`
is the right tool for ephemeral state in every pattern, including MVN and Bloc.
`TextEditingController`, `AnimationController` and friends belong in a `State`
or a hook, not in a provider (ARCH-109).

An app that uses only `setState` is the `setstate` profile. That's fine for
small apps. Flag only concrete harm:

- I/O in `State` classes (ARCH-101, `AP-massive-view`)
- the same data loaded and held by several screens (`AP-two-sources-of-truth`)
- state lifted so far that a root `setState` rebuilds the whole app

When it starts to hurt, the cheapest next step is a repository plus a
`ChangeNotifier` per screen, which is Flutter MVVM. `InheritedWidget` /
`InheritedNotifier` is what `provider` wraps; hand-rolled ones are fine for DI
of a few objects.

## 6. GetX

GetX bundles state management (`.obs` + `Obx`, `GetBuilder` + `update()`), a
global service locator (`Get.put`, `Get.lazyPut`, `Get.find`, `Bindings`), and
context-free navigation and overlays (`Get.to`, `Get.snackbar`). Its idioms
make some rules inapplicable:

| Rule | Under getx |
|---|---|
| ARCH-104 service-locator-in-ui | **Off.** `Get.find`/`GetView` in widgets is the idiom |
| ARCH-102 context-in-logic | `Get.` navigation in controllers is **not** flagged; a `BuildContext` field still is |
| ARCH-009 logic-depends-on-flutter-ui | Low: GetX controllers often import Flutter for `TextEditingController` |
| ARCH-109 ephemeral-state-in-provider | Doesn't apply: controllers owning text controllers (and closing them in `onClose`) is idiomatic |
| ARCH-113 getx-in-build | **On**: `Get.put`/`Get.find` in `build()` |
| `AP-getx-service-locator-everywhere` | `Get.find` in repositories, models, services or deep in controller methods |

Dispose what you create in `onClose()`. Register in `Bindings`, not ad hoc.
Inject repositories into controllers through the constructor.

## 7. Others: hooks, signals, stacked, MobX, Redux

- **flutter_hooks** (`HookWidget`, `useTextEditingController`, `useState`):
  ephemeral widget state; recommended by riverpod.dev for exactly that. Not an
  architecture.
- **signals**: fine-grained reactive values; named by the Flutter case study as
  an alternative to `ChangeNotifier` in MVVM.
- **stacked**: an MVVM framework (`BaseViewModel`, `ViewModelBuilder`). Profile
  `mvvm`; review with `mvvm.md`.
- **MobX** (`Store`, `@observable`, `@action`): view-model-like stores (the
  `_store` suffix is classified as logic). Review as MVVM.
- **Redux** (`flutter_redux`): a single store, reducers, middleware for side
  effects. Not covered by a profile; review reducers for purity and middleware
  for I/O placement, and say the profile was `unknown`.

## 8. Mixing libraries

- Two state-management libraries for the **same job** (Riverpod notifiers and
  Bloc cubits both holding screen state) is one Medium finding
  (`AP-mixed-architecture`), reported once.
- Two libraries for **different jobs** is normal: Riverpod for app state +
  `setState`/hooks for ephemeral state; `flutter_bloc` + `get_it` for DI;
  `provider` for DI under `ChangeNotifier` view models.
- A migration in progress is Info if documented.

## 9. Choosing one

When the project has none and asks:

- **Small app or prototype**: `setState`, plus `ChangeNotifier` when two widgets
  need the same state.
- **Following the Flutter team**: `ChangeNotifier` view models + `provider`
  for DI (Flutter MVVM).
- **Compile-safe DI, async state built in, testing by override**: Riverpod;
  add the MVN pattern if the team wants strict layering and codegen.
- **Explicit events, traceability, large teams used to Bloc**: flutter_bloc.
- **GetX**: works, but its global service locator and implicit context make
  dependencies hard to see and test. If a team picks it, insist on bindings and
  constructor injection.

The Flutter team's own verdict: `ChangeNotifier` is "Conditional", and any
mainstream state solution is fine. Choose what the team will apply
consistently.
