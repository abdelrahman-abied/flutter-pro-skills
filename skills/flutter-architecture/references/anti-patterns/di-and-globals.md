# Anti-patterns: DI and globals

How dependencies are found: service locators called from the UI, global mutable state, and singletons reached from everywhere.

Part of the architecture anti-pattern catalog. The index, [`references/anti-patterns.md`](../anti-patterns.md), holds the severity scale, the profile rules and a table of every ID; read it first.

### ARCH-104 service-locator-in-ui

**Low** · applies: all except getx · detect: arch_check (regex: `GetIt.I`,
`GetIt.instance`, `getIt<`, `getIt(`, `sl<`, `locator<`, `Get.find<` in views
and widgets)

**Problem.** Widgets pull dependencies from a global locator.
**Why.** Dependencies become invisible in the widget's API, widget tests must
configure the global, and widgets grab repositories they shouldn't see. The
Flutter team rates "dependency injection, with no globally accessible
objects" Strong.

```dart
// Bad
class OrdersScreen extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    final vm = GetIt.I<OrdersViewModel>();
    return OrdersList(viewModel: vm);
  }
}
```

```dart
// Good
class OrdersScreen extends StatelessWidget {
  const OrdersScreen({super.key, required this.viewModel}); // built at the route
  final OrdersViewModel viewModel;
  @override
  Widget build(BuildContext context) => OrdersList(viewModel: viewModel);
}
```

**Fix.** Resolve from the locator only in the composition root (router,
`main`), and pass objects down by constructor or provider.
**False positives.** Under getx it's the idiom (`GetView`, `Get.find`); see
ARCH-113 for the real GetX problem.

### ARCH-105 global-mutable-state

**Medium** · applies: all · detect: arch_check (regex: top-level non-final
variables in `lib/`, non-final `static` fields outside Flutter `State`)

**Problem.** Mutable globals (`User? currentUser;` at top level,
`static String? token;`).
**Why.** Anyone can change them, nothing is notified, tests leak state into
each other, and there's no single owner.

```dart
// Bad
User? currentUser;
class Session { static String? token; }
```

```dart
// Good
abstract interface class SessionRepository {
  Stream<User?> watchUser();
  Future<String?> token();
}
// one instance, owned by DI (Provider / @riverpod / get_it), injected where needed
```

**Fix.** Move the state into a repository or provider with a single owner and
change notification.
**False positives.** `late final` top-level values set once at startup are
final. The `mvc_pattern` controller-singleton idiom (`static Controller? _this`)
fires this rule; report it as Info if the project uses the idiom consistently.

### AP-singleton-abuse

**Medium** · applies: all · detect: reading

**Problem.** Classes reached through a global accessor everywhere:
`ApiClient.instance`, `factory Db() => _instance`, `AnalyticsService.shared`.
**Why.** Global *access*, not single *lifetime*, is the problem: every caller
hard-wires the concrete class, you can't substitute a fake, and initialisation
order bugs appear.

```dart
// Bad
class CartRepository {
  Future<Cart> load() => ApiClient.instance.get('/cart').then(Cart.fromJson);
}
```

```dart
// Good
final class CartRepositoryRemote implements CartRepository {
  const CartRepositoryRemote(this._api); // one ApiClient, created and owned by DI
  final ApiClient _api;
}
```

**Fix.** Keep the single instance, but create it in the composition root and
inject it.
**False positives.** SDK and plugin singletons (`FirebaseAuth.instance`)
accessed only inside one service class that wraps them; that service is the
seam.
