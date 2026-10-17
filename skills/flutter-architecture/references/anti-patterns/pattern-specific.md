# Anti-patterns: Pattern-specific

Rules that only make sense inside one pattern: Bloc (blocs coupled to blocs, sibling logic), MVN (use cases, naming, codegen syntax), Riverpod (provider init, dynamic providers, side effects in `build`), GetX, MVC and MVVM, plus two patterns used for one job. Check each entry's profile line before reporting. Files that entries mention by bare name, such as `detect.md`, are siblings of the index in `references/`.

Part of the architecture anti-pattern catalog. The index, [`references/anti-patterns.md`](../anti-patterns.md), holds the severity scale, the profile rules and a table of every ID; read it first.

## Contents

- [ARCH-010 sibling-logic-dependency](#arch-010-sibling-logic-dependency)
- [AP-bloc-to-bloc](#ap-bloc-to-bloc)
- [ARCH-012 mvn-notifier-bypasses-usecase](#arch-012-mvn-notifier-bypasses-usecase)
- [ARCH-112 mvn-forbidden-naming](#arch-112-mvn-forbidden-naming)
- [AP-mvn-legacy-riverpod-syntax](#ap-mvn-legacy-riverpod-syntax)
- [ARCH-110 provider-init-from-widget](#arch-110-provider-init-from-widget)
- [AP-riverpod-dynamic-providers](#ap-riverpod-dynamic-providers)
- [AP-riverpod-side-effects-in-provider-build](#ap-riverpod-side-effects-in-provider-build)
- [ARCH-113 getx-in-build](#arch-113-getx-in-build)
- [AP-getx-service-locator-everywhere](#ap-getx-service-locator-everywhere)
- [AP-mvc-massive-controller](#ap-mvc-massive-controller)
- [AP-viewmodel-exposes-repository](#ap-viewmodel-exposes-repository)
- [AP-mixed-architecture](#ap-mixed-architecture)

### ARCH-010 sibling-logic-dependency

**Medium** under bloc; **Low** under mvvm, mvc, getx · doesn't apply: **mvn,
riverpod** (the MVN spec sanctions `ref.watch(otherProvider)` in `build()`) ·
detect: arch_check (import between logic files, excluding a file's own
state/event `part`s)

**Problem.** One logic class imports another: a bloc taking a bloc, a view
model holding a view model.
**Why.** Bloc: "no bloc should know about any other bloc"; sibling
dependencies in one layer "should be avoided at all costs". In MVVM, a view
model belongs to one view and gets data from repositories. The coupling makes
lifetimes and tests depend on each other.

```dart
// Bad (MVVM)
class CheckoutViewModel extends ChangeNotifier {
  CheckoutViewModel(this._cart); // another screen's view model
  final CartViewModel _cart;
}
```

```dart
// Good: both read the shared repository
class CheckoutViewModel extends ChangeNotifier {
  CheckoutViewModel({required CartRepository cart}) : _cart = cart;
  final CartRepository _cart; // exposes Stream<Cart>
}
```

**Fix.** Share through a repository (stream), or connect in the presentation
layer (`BlocListener`). Under MVN/Riverpod the reactive `ref.watch` link is the
answer, not a finding.
**False positives.** Importing another logic file only for a shared enum or
typedef; move it to `domain/` or `core/`.

### AP-bloc-to-bloc

**Medium** · applies: bloc · doesn't apply: mvn, riverpod (reactive links
sanctioned) · detect: reading (the counterpart of ARCH-010, which only sees
imports)

**Problem.** A bloc subscribes to another bloc's `stream`, receives a bloc in
its constructor (often via `context.read<FirstBloc>()` in `BlocProvider`),
or calls `otherBloc.add(...)`.
**Why.** bloclibrary: "You should **not** do this." A bloc "should only
receive information through events and from injected repositories."

```dart
// Bad
BlocProvider(
  create: (context) => ThemeBloc(weatherBloc: context.read<WeatherBloc>()),
);
```

```dart
// Good: through presentation
BlocListener<WeatherBloc, WeatherState>(
  listener: (context, state) => context.read<ThemeCubit>().updateTheme(state.weather),
  child: const WeatherView(),
);
// or through domain: both blocs subscribe to WeatherRepository's stream
```

**Fix.** Push the coordination up (a `BlocListener`) or down (a reactive
repository).
**False positives.** None under the bloc profile; in a mixed app make sure the
"bloc" isn't a Riverpod notifier.

### ARCH-012 mvn-notifier-bypasses-usecase

**Medium** · applies: **mvn only** · doesn't apply: mvvm, bloc, riverpod, and
everything else (where logic may call repositories) · detect: arch_check
(import)

**Problem.** A notifier imports a repository contract, repository
implementation, source or service instead of a use case.
**Why.** The MVN spec's runtime flow is View → Notifier → UseCase → Repository
→ Source; a notifier has "no raw repository/source access". The use-case
provider is also the DI seam tests override.

```dart
// Bad
import '../../domain/repositories/movie_repository.dart';
import '../../data/repositories/movie_repository_impl.dart';

final movies = await ref.read(movieRepositoryProvider).fetchTrending();
```

```dart
// Good
import '../../domain/usecases/movie_usecase.dart';

final movies = await ref.read(fetchTrendingMoviesProvider)();
```

**Fix.** Add (or use) the use case for that intent, with its `@riverpod`
provider in `domain/usecases/`.
**False positives.** None under mvn. Under any other profile this is not a
finding.

### ARCH-112 mvn-forbidden-naming

**Low** · applies: **mvn only** · doesn't apply: Flutter's own controllers
declared as fields (`AnimationController`, `TextEditingController`), any
non-MVN profile · detect: arch_check (regex on class names and folders)

**Problem.** Classes ending in `ViewModel`, `VM` or `Controller`, or
`controller(s)/`/`view_model(s)/` folders, in an MVN app.
**Why.** The spec: the bridge is a `Notifier`, "never a ViewModel, Controller,
or VM", and the folder is `notifier/`. Mixed vocabulary hides which pattern a
file follows.

```dart
// Bad: presentation/controllers/movie_controller.dart
@riverpod
class MovieController extends _$MovieController { /* ... */ }
```

```dart
// Good: presentation/notifier/movie_notifier.dart
@riverpod
class MovieNotifier extends _$MovieNotifier { /* ... */ }
```

**Fix.** Rename the class and move it to `presentation/notifier/`. Naming
tables are in the `dart-naming` skill.
**False positives.** Fields typed with Flutter controllers are allowed; a
`ScrollController` *class* declared by the app (rare) is also a Flutter-style
controller.

### AP-mvn-legacy-riverpod-syntax

**Low** · applies: **mvn** (under plain riverpod: Info, only if both styles are
mixed) · detect: reading

**Problem.** `StateNotifier`/`StateNotifierProvider`, `ChangeNotifierProvider`,
hand-written `Provider((ref) => …)`, or per-provider `*Ref` types on
Riverpod 3, in an MVN app.
**Why.** The spec mandates "modern syntax only": `@riverpod` + `part
'….g.dart'`, notifiers extending `_$Name`, the generic `Ref`.

```dart
// Bad
final movieProvider = StateNotifierProvider<MovieNotifier, MovieState>(
  (ref) => MovieNotifier(ref.watch(fetchTrendingMoviesProvider)),
);
class MovieNotifier extends StateNotifier<MovieState> { /* ... */ }
```

```dart
// Good
part 'movie_notifier.g.dart';

@riverpod
class MovieNotifier extends _$MovieNotifier {
  @override
  MovieState build() => const MovieInitial();
}
```

**Fix.** Migrate to codegen and run `dart run build_runner build -d`.
**False positives.** Generated `*.g.dart` content; third-party packages.

### ARCH-110 provider-init-from-widget

**Low** · applies: riverpod, mvn · detect: arch_check (regex: `ref.read(…)`
followed by a call inside `initState()`)

**Problem.** A widget's `initState` initialises a provider:
`ref.read(p.notifier).load()`.
**Why.** riverpod.dev: "AVOID initializing providers in a widget. Providers
should initialize themselves." Doing it from a widget causes race conditions
and re-initialisation when the widget re-mounts.

```dart
// Bad
@override
void initState() {
  super.initState();
  ref.read(ordersNotifierProvider.notifier).load();
}
```

```dart
// Good
@riverpod
class OrdersNotifier extends _$OrdersNotifier {
  @override
  Future<List<Order>> build() => ref.watch(getOrdersProvider)(); // loads itself
}
// or, when init depends on the user's action, call it in the onPressed that navigates
```

**Fix.** Load in the provider's `build()` (an `AsyncNotifier` or
`FutureProvider` for reads), or trigger from the action that leads to the
screen.
**False positives.** One-shot *non-initialising* calls in `initState`
(analytics `screenViewed()`) are judgment calls; MVN's golden template loads
from a button, which is also fine. The checker also fires when the call is
wrapped in `addPostFrameCallback` inside `initState` (for example, applying a
route argument). Read those individually: forwarding a route argument once is
often acceptable.

### AP-riverpod-dynamic-providers

**Medium** · applies: riverpod, mvn · detect: reading

**Problem.** Providers created inside classes, functions or `build()`, or
passed around as constructor arguments and watched dynamically.
**Why.** riverpod.dev: providers "should exclusively be top-level final
variables"; a provider created as a field "could cause memory leaks and
unexpected behaviors". Dynamic providers also defeat `riverpod_lint`.

```dart
// Bad
class ProductTile extends ConsumerWidget {
  ProductTile(this.id, {super.key});
  final String id;
  late final _price = FutureProvider((ref) => ref.watch(apiProvider).price(id));
  @override
  Widget build(BuildContext context, WidgetRef ref) => Text('${ref.watch(_price).value}');
}
```

```dart
// Good
@riverpod
Future<Money> productPrice(Ref ref, String id) =>
    ref.watch(getPriceProvider)(id); // a family, declared once at top level

// in the widget
final price = ref.watch(productPriceProvider(id));
```

**Fix.** Declare providers at top level; parameterise with families (codegen
parameters).
**False positives.** `static final` providers are allowed by Riverpod (not by
the code generator).

### AP-riverpod-side-effects-in-provider-build

**High** · applies: riverpod, mvn · detect: reading

**Problem.** A provider's or notifier's `build()` performs a write: posts a
form, sends analytics, deletes a record, navigates.
**Why.** riverpod.dev: "DON'T perform side effects during the initialization of
a provider. Providers should generally be used to represent a 'read'
operation." Providers rebuild when dependencies change and may be disposed and
re-created, so the write can repeat, or be skipped if a previous one was
cached.

```dart
// Bad
@riverpod
Future<void> submitOrder(Ref ref) async {
  final form = ref.watch(orderFormProvider);
  await ref.watch(orderApiProvider).post(form.toJson()); // re-posts when the form changes
}
```

```dart
// Good
@riverpod
class CheckoutNotifier extends _$CheckoutNotifier {
  @override
  CheckoutState build() => const CheckoutIdle();

  Future<void> submit(OrderForm form) async { // a method: runs once, when called
    state = const CheckoutSubmitting();
    try {
      await ref.read(submitOrderProvider)(form);
      state = const CheckoutDone();
    } catch (e) {
      state = CheckoutFailed('$e');
    }
  }
}
```

**Fix.** Writes go in notifier methods (or Riverpod 3 mutations); `build()`
only reads.
**False positives.** Reads with incidental caching, and setting up
subscriptions with `ref.onDispose` cleanup, are fine in `build()`.

### ARCH-113 getx-in-build

**Low** · applies: getx · detect: arch_check (regex: `Get.put(`/`Get.find(`
inside `build(`)

**Problem.** A widget registers or looks up a GetX dependency inside `build()`.
**Why.** `build()` runs often. `Get.put` there re-registers (and may recreate)
the controller on rebuild; lookups hide the dependency and fail late if the
binding didn't run.

```dart
// Bad
@override
Widget build(BuildContext context) {
  final c = Get.put(CartController());
  return Obx(() => Text('${c.count}'));
}
```

```dart
// Good
class CartView extends GetView<CartController> { // registered by CartBinding
  const CartView({super.key});
  @override
  Widget build(BuildContext context) => Obx(() => Text('${controller.count}'));
}
```

**Fix.** Register in a `Bindings` class attached to the route; read it via
`GetView`/a field initialised once.
**False positives.** `Get.find` inside a callback defined in `build()` (an
`onPressed`) runs on tap, not on every build. Read the context of the match.

### AP-getx-service-locator-everywhere

**Medium** · applies: getx (and `get_it`-heavy apps of any profile) · detect:
reading

**Problem.** `Get.find<T>()` is called from repositories, models, services and
deep inside controller methods, so the dependency graph lives in a global map.
**Why.** Dependencies are invisible, order of registration matters at runtime,
and tests must configure global state (`Get.reset()`) for every case.

```dart
// Bad
class OrderRepository {
  Future<List<Order>> list() => Get.find<ApiClient>().get('/orders').then(_parse);
}
class OrdersController extends GetxController {
  void refreshAll() => Get.find<OrderRepository>().list().then(orders.assignAll);
}
```

```dart
// Good
final class OrderRepository {
  const OrderRepository(this._api);
  final ApiClient _api;
}
final class OrdersController extends GetxController {
  OrdersController(this._orders); // wired in OrdersBinding
  final OrderRepository _orders;
}
```

**Fix.** Use the locator only in bindings (the composition root); pass
dependencies through constructors everywhere else.
**False positives.** `Get.find` in a widget is the GetX idiom (ARCH-104 is
off under getx).

### AP-mvc-massive-controller

**Medium** · applies: mvc, getx · detect: reading (ARCH-103, ARCH-007 and
ARCH-102 are the mechanical symptoms)

**Problem.** The controller does everything: HTTP calls, JSON parsing,
validation, formatting, navigation, and state for several screens.
**Why.** MVC's classic failure (iOS's "Massive View Controller"): with no other
sanctioned home for logic, it all lands in the controller, which becomes
untestable and a merge-conflict magnet.

```dart
// Bad
class ShopController extends GetxController {
  final products = <Map<String, dynamic>>[].obs;
  Future<void> load() async {
    final res = await Dio().get('https://api.shop.com/products');
    products.assignAll((res.data as List).cast());
  }
  String priceLabel(Map<String, dynamic> p) => '\$${(p['cents'] / 100).toStringAsFixed(2)}';
  void checkout() { /* validation, payment, Get.toNamed('/receipt') ... */ }
}
```

```dart
// Good
final class ProductsController extends GetxController {
  ProductsController(this._products);
  final ProductRepository _products;          // Dio + JSON live in ProductApi / the repository
  final products = <Product>[].obs;           // domain models, formatted in the view
  Future<void> load() async => products.assignAll(await _products.list());
}
// checkout gets its own CheckoutController
```

**Fix.** Services do I/O, repositories map and cache, one controller per
screen or flow, formatting in the view.
**False positives.** A long controller for one genuinely complex screen with
no I/O inside may be fine; check responsibilities, not just length.

### AP-viewmodel-exposes-repository

**Low** (raise to Medium if views actually call through it) · applies: mvvm,
bloc, mvc, getx · doesn't apply: mvn (notifiers don't hold repositories) ·
detect: reading

**Problem.** A logic class exposes its repository or service as a public field.
**Why.** The Flutter case study: repositories "should be private members on the
view model, otherwise views would have direct access to the data layer".

```dart
// Bad
class HomeViewModel extends ChangeNotifier {
  HomeViewModel(this.bookingRepository);
  final BookingRepository bookingRepository; // view can call it directly
}
```

```dart
// Good
class HomeViewModel extends ChangeNotifier {
  HomeViewModel({required BookingRepository bookingRepository})
      : _bookingRepository = bookingRepository;
  final BookingRepository _bookingRepository;
}
```

**Fix.** Make it private and expose commands/state instead.
**False positives.** None.

### AP-mixed-architecture

**Medium** (documented, ongoing migration: **Info**) · applies: all · detect:
reading (the profile's `signals` and `state_management` often show it)

**Problem.** Two presentation patterns or state libraries do the same job in
one app: MVVM view models in some features, MVN notifiers in others; Bloc and
GetX side by side.
**Why.** Two vocabularies, two DI mechanisms, two test styles; every new
feature reopens the choice. Report it **once**, with the feature lists, not on
every file. See `detect.md` §8.

```text
Bad:  features/auth, profile    → *ViewModel extends ChangeNotifier (provider DI)
      features/catalog, cart    → @riverpod *Notifier (Riverpod DI)
```

```text
Good: one declared pattern in the project instructions file; the minority
      features migrate when next touched; new features follow the target pattern
```

**Fix.** Pick the target (usually the majority), record it, migrate
incrementally.
**False positives.** Different libraries for *different* jobs (Riverpod for
app state, `setState`/hooks for ephemeral state) is normal.
