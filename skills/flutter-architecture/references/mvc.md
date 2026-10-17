# MVC in Flutter (including GetX-style controllers)

Flutter has **no official MVC guidance**. docs.flutter.dev recommends MVVM.
MVC shows up in Flutter apps in three forms, and this file covers all of them:

1. **Packages built for it**: `mvc_pattern` (`StateMVC`, `ControllerMVC`) and
   its successors `fluttery_framework` / `state_extended` (`StateX`,
   `StateXController`).
2. **GetX** (`GetxController`, `Obx`, `Get.put`/`Get.find`): controller-centred
   and MVC-flavoured, with its own idioms. GetX state specifics are also in
   `state-management.md`.
3. **Hand-rolled**: `lib/{models,views,controllers}/` with
   `XController extends ChangeNotifier`. This is usually MVVM in all but name;
   judging it by `mvvm.md`'s rules is fair.

What follows is established MVC practice applied to Flutter, not a canonical
Flutter source. Report findings at "recommendation" strength, except where
they're universal (I/O in widgets, domain depending on UI).

## Contents

1. What it is
2. Layers and roles
3. Allowed dependencies
4. Folder layouts
5. State, events and side effects
6. DI and testing
7. The Massive Controller
8. Pattern-specific anti-patterns
9. Good examples
10. Reviewing an MVC or GetX codebase

## 1. What it is

Classic MVC (Trygve Reenskaug, Smalltalk, late 1970s) splits an interactive
program into:

- **Model**: the domain data and rules. It notifies observers when it changes
  and knows nothing about the UI.
- **View**: renders the model and observes it for changes.
- **Controller**: interprets user input and turns it into operations on the
  model (and, in later variants, chooses which view to show).

In a declarative framework like Flutter, the "view observes the model" link is
usually replaced by "the controller exposes state and triggers a rebuild",
which is why Flutter MVC drifts toward MVVM.

## 2. Layers and roles

| Role | In Flutter |
|---|---|
| **Model** | Immutable domain models plus the repositories/services that load and change them |
| **Controller** | A non-widget class holding screen logic: `ControllerMVC`/`StateXController`, `GetxController`, or `ChangeNotifier`. Calls the model layer, holds UI state, triggers rebuilds |
| **View** | Widgets. `StateMVC<T>`/`StateX<T>` (a `State` that owns controllers), `GetView<C>`/`Obx`, or a `StatelessWidget` given a controller |

## 3. Allowed dependencies

| From ↓ may use → | View | Controller | Repository / service | Model |
|---|---|---|---|---|
| **View** | yes | yes (its controller) | no | read it (display) |
| **Controller** | no widgets, no `BuildContext` (GetX navigation excepted) | avoid sibling controllers | yes | yes |
| **Repository / service** | no | no | no other repositories | yes |
| **Model** | no | no | no | yes |

Same core as every pattern: views don't do I/O; the model layer knows nothing
about controllers or views; repositories don't know each other.

## 4. Folder layouts

Hand-rolled or `mvc_pattern`:

```text
lib/
├── models/          # domain models
├── services/        # API clients, storage (often also repositories/)
├── controllers/     # *Controller classes (not Flutter's own controllers)
├── views/           # screens
└── widgets/
```

GetX with `get_cli` (feature modules under `lib/app/`):

```text
lib/app/
├── data/            # models, providers (API), repositories
├── modules/<module>/
│   ├── bindings/<module>_binding.dart        # Get.lazyPut(() => HomeController())
│   ├── controllers/<module>_controller.dart  # extends GetxController
│   └── views/<module>_view.dart              # extends GetView<HomeController>
└── routes/          # app_pages.dart, app_routes.dart
```

Note for the checker: `app` is a composition-root path segment, so in a get_cli
layout files such as `modules/<m>/controllers/*.dart` can be classified as
composition root and skip the import rules (ARCH-007 would miss a controller
importing `dio`). Read the controllers yourself (`detect.md` §7).

## 5. State, events and side effects

- **mvc_pattern / StateX**: the view's `State` (`StateMVC`/`StateX`) registers
  its controller; the controller changes data and calls `setState` (exposed on
  the controller) to rebuild the view. Events are controller method calls.
- **GetX**: reactive fields (`final count = 0.obs;`) rebuild `Obx` widgets;
  `update()` rebuilds `GetBuilder`s. One-time effects are idiomatic GetX calls
  from the controller (`Get.snackbar`, `Get.toNamed`) or workers (`ever`,
  `once`, `debounce`, `interval`) registered in `onInit`. That's why ARCH-102
  doesn't fire for `Get.` navigation under the getx profile, and ARCH-009 is
  only low there.
- **Hand-rolled ChangeNotifier controllers**: as MVVM: the view listens
  (`ListenableBuilder`) and handles one-time effects with a listener.

Whatever the flavour, keep state immutable where the framework allows it, and
model loading/error explicitly rather than as loose flags
(`AP-boolean-soup-state`).

## 6. DI and testing

- **GetX**: `Bindings` per route register controllers with `Get.lazyPut`, and
  repositories with `Get.put`/`Get.lazyPut(fenix: true)`; widgets get the
  controller via `GetView<C>` or `Get.find<C>()`. Keep `Get.find` out of
  repositories and models, and inject repositories into controllers through
  the constructor so they can be faked (`AP-getx-service-locator-everywhere`).
  In tests, register fakes with `Get.put<Repo>(FakeRepo())` and call
  `Get.reset()` in `tearDown`.
- **mvc_pattern**: the package's examples often make controllers singletons
  (`factory Controller() => _this ??= Controller._();`). It's an accepted idiom
  there, but it makes tests share state; prefer constructor injection for the
  repositories the controller uses.
- **Hand-rolled**: inject through constructors at the composition root, as in
  MVVM.

## 7. The Massive Controller

The characteristic MVC failure (iOS developers know it as Massive View
Controller): the controller becomes the only place logic can go, so it fills
with networking, parsing, validation, formatting, navigation and state for
several screens. Symptoms:

- one controller per app area, hundreds of lines (ARCH-103)
- `Dio`, `http` or `SharedPreferences` used directly in the controller
  (ARCH-007)
- `BuildContext` parameters and `Navigator` calls (ARCH-102)
- several screens `Get.find` the same controller and read different parts of it

Fix by giving each layer its job back: services do I/O, repositories map and
cache, the controller orchestrates one screen. See `AP-mvc-massive-controller`.

## 8. Pattern-specific anti-patterns

| ID | In MVC / GetX |
|---|---|
| `AP-mvc-massive-controller`, ARCH-103 | One controller doing everything |
| ARCH-007 | Controller imports `dio`/`http`/a source instead of a repository |
| ARCH-102 | `BuildContext` or `Navigator` in a controller (mvc); for getx, `Get.` navigation is fine |
| ARCH-009 | Controller imports `material.dart` (medium; low under getx) |
| ARCH-104 | `Get.find`/`GetIt.I` in widgets: **not** flagged under getx, where it's the idiom |
| ARCH-113 | `Get.put`/`Get.find` inside `build()`: re-registers on every rebuild |
| `AP-getx-service-locator-everywhere` | `Get.find` in repositories, models, other controllers |
| ARCH-010 (low) | A controller importing another controller |
| ARCH-008 | A view importing a repository |

ARCH-112 (forbidden `Controller` naming) is MVN-only. Controllers are the
correct vocabulary here.

## 9. Good examples

GetX:

```dart
// app/modules/profile/controllers/profile_controller.dart
final class ProfileController extends GetxController {
  ProfileController(this._users); // injected, so tests can pass a fake
  final UserRepository _users;

  final state = Rx<ProfileState>(const ProfileLoading());

  @override
  void onInit() {
    super.onInit();
    load();
  }

  Future<void> load() async {
    state.value = const ProfileLoading();
    state.value = switch (await _users.getMe()) {
      Ok(:final value) => ProfileLoaded(value),
      Error(:final error) => ProfileFailed(error.toString()),
    };
  }
}

// app/modules/profile/bindings/profile_binding.dart
final class ProfileBinding extends Bindings {
  @override
  void dependencies() =>
      Get.lazyPut(() => ProfileController(Get.find<UserRepository>()));
}

// app/modules/profile/views/profile_view.dart
class ProfileView extends GetView<ProfileController> {
  const ProfileView({super.key});

  @override
  Widget build(BuildContext context) => Obx(
        () => switch (controller.state.value) {
          ProfileLoading() => const Center(child: CircularProgressIndicator()),
          ProfileLoaded(:final user) => UserCard(user: user),
          ProfileFailed(:final message) =>
            ErrorView(message: message, onRetry: controller.load),
        },
      );
}
```

Hand-rolled MVC with `ChangeNotifier`:

```dart
final class CartController extends ChangeNotifier {
  CartController({required CartRepository cart}) : _cart = cart;
  final CartRepository _cart;

  CartState _state = const CartLoading();
  CartState get state => _state;

  Future<void> remove(String itemId) async {
    _state = switch (await _cart.remove(itemId)) {
      Ok(:final value) => CartLoaded(value),
      Error(:final error) => CartFailed(error.toString()),
    };
    notifyListeners();
  }
}
```

## 10. Reviewing an MVC or GetX codebase

- [ ] Controllers orchestrate one screen or flow and stay under the size
      limits; I/O lives in services/repositories.
- [ ] Controllers receive repositories through the constructor (or a
      `Binding`), not by calling `Get.find` deep inside methods.
- [ ] No `BuildContext` in controllers (except GetX's context-free navigation
      under the getx profile).
- [ ] Views contain no I/O and no business rules; they render controller
      state and forward events.
- [ ] GetX: no `Get.put`/`Get.find` in `build()`; bindings own registration;
      `Get.reset()` in tests.
- [ ] Repositories return domain models and don't import each other.
- [ ] Loading/error state is explicit (sealed state or a status enum), not
      scattered bools.
