# Anti-patterns: Dependency rule

Import-direction rules: which layer may import which, and which feature may reach into which. `scripts/arch_check.py` checks the `ARCH-*` entries from the import graph; the two `AP-*` entries are found by reading. Each rule only applies when the project has the layer or feature split it assumes, so check the profile line before reporting.

Part of the architecture anti-pattern catalog. The index, [`references/anti-patterns.md`](../anti-patterns.md), holds the severity scale, the profile rules and a table of every ID; read it first.

## Contents

- [ARCH-001 domain-depends-on-data](#arch-001-domain-depends-on-data)
- [ARCH-002 domain-depends-on-presentation](#arch-002-domain-depends-on-presentation)
- [ARCH-003 domain-depends-on-framework](#arch-003-domain-depends-on-framework)
- [ARCH-004 data-depends-on-presentation](#arch-004-data-depends-on-presentation)
- [ARCH-013 core-depends-on-feature](#arch-013-core-depends-on-feature)
- [ARCH-014 cross-feature-internal-import](#arch-014-cross-feature-internal-import)
- [ARCH-015 feature-cycle](#arch-015-feature-cycle)
- [AP-feature-envy-across-features](#ap-feature-envy-across-features)
- [AP-context-passed-down-to-data](#ap-context-passed-down-to-data)

### ARCH-001 domain-depends-on-data

**High** · applies: wherever a domain layer exists · doesn't apply: the MVN
use-case provider seam · detect: arch_check (import)

**Problem.** A file under `domain/` imports a file under `data/`: a DTO, a
repository implementation, a source.
**Why.** The domain is the stable centre. Once it imports data, a change to an
API model or a database package ripples into business rules, and the domain
can't be tested without the data layer. It defeats Clean Architecture's one
non-negotiable rule.

```dart
// Bad: lib/features/movie/domain/usecases/get_movies.dart
import '../../data/models/movie_response.dart';
import '../../data/repositories/movie_repository_impl.dart';

class GetMovies {
  final MovieRepositoryImpl _repo;      // concrete data class
  Future<List<MovieResponse>> call() => _repo.fetch(); // DTO in the domain
}
```

```dart
// Good
import '../entities/movie_entity.dart';
import '../repositories/movie_repository.dart'; // the domain's own contract

final class GetMovies {
  const GetMovies(this._repo);
  final MovieRepository _repo;
  Future<List<MovieEntity>> call() => _repo.fetchTrending();
}
```

**Fix.** Depend on a contract declared in `domain/repositories/`, return
entities, and bind the implementation in the composition root.
**False positives.** Under MVN, a `@riverpod` use-case provider in
`domain/usecases/` importing the repository implementation's provider is the
spec's DI seam; arch_check puts it in `suppressed`. The use-case *class* must
still not touch data types.

### ARCH-002 domain-depends-on-presentation

**High** · applies: wherever a domain layer exists · detect: arch_check (import)

**Problem.** A domain file imports presentation: a notifier, bloc, view model,
state class or widget.
**Why.** Business rules now depend on how one screen happens to be built. MVN's
spec says domain code "must never `watch`/`read` UI state or notifiers".

```dart
// Bad: domain/usecases/apply_coupon.dart
import '../../presentation/notifier/cart_notifier.dart';

final class ApplyCoupon {
  ApplyCoupon(this._ref);
  final Ref _ref;
  Future<void> call(String code) async {
    final cart = _ref.read(cartNotifierProvider); // domain reading UI state
  }
}
```

```dart
// Good
final class ApplyCoupon {
  const ApplyCoupon(this._coupons);
  final CouponRepository _coupons;
  Future<Cart> call(Cart cart, String code) async =>
      cart.withDiscount(await _coupons.lookup(code));
}
```

**Fix.** Pass the data the rule needs as parameters; let the presentation layer
call the use case with its current state.
**False positives.** None known; a domain type that merely shares a name with a
presentation file may be misclassified by an unusual folder name.

### ARCH-003 domain-depends-on-framework

**Medium** (`package:flutter/foundation.dart`: **Low**) · applies: wherever a
domain layer exists · doesn't apply: `riverpod_annotation`/`riverpod` in
`domain/usecases/` under mvn · detect: arch_check (import)

**Problem.** A domain file imports `package:flutter/*`, an I/O package (`dio`,
`http`, `sqflite`, `firebase_*`, `shared_preferences` …), or a state-management
package (`flutter_riverpod`, `hooks_riverpod`, `flutter_bloc`, `provider`, `get`).
**Why.** The domain should run in a plain `dart test` and survive a change of
UI toolkit, transport or state library.

```dart
// Bad: domain/entities/product.dart
import 'package:flutter/material.dart';

class Product {
  final String name;
  final Color badgeColor; // a UI concern in an entity
}
```

```dart
// Good
import 'package:meta/meta.dart';

enum ProductTier { standard, premium }

@immutable
final class Product {
  const Product({required this.name, required this.tier});
  final String name;
  final ProductTier tier; // the view maps tier → colour
}
```

**Fix.** Use `package:meta` for `@immutable`, pure-Dart value types, and map to
UI types in presentation.
**False positives.** `foundation.dart` for `@immutable`/`listEquals` is a Low
finding: it pulls in Flutter for little gain. Pure-Dart packages (`equatable`,
`freezed_annotation`, `fpdart`, `collection`) are fine.

### ARCH-004 data-depends-on-presentation

**High** · applies: all · detect: arch_check (import)

**Problem.** A data-layer file (repository, service, source, DTO) imports a
presentation file.
**Why.** The data layer would have to change whenever a screen does, and it can
no longer be reused or tested without the UI. Data flows up; it doesn't reach up.

```dart
// Bad: data/repositories/cart_repository_impl.dart
import '../../presentation/state/cart_state.dart';

Future<CartState> load() async =>
    CartLoaded((await _api.cart()).toEntity()); // repository builds UI state
```

```dart
// Good
Future<Cart> load() async => (await _api.cart()).toEntity();
// the notifier / view model turns Cart into CartLoaded
```

**Fix.** Return domain models; let the logic layer map them to UI state.
**False positives.** A layer-first project whose `models/` folder holds UI-only
classes can be misclassified as data. Read before reporting.

### ARCH-013 core-depends-on-feature

**Medium** · applies: feature-first, hybrid layouts · detect: arch_check (import)

**Problem.** A file in `core/`, `shared/` or `common/` imports something under
`features/`.
**Why.** Every feature depends on core. If core depends on a feature, every
feature transitively depends on that feature, and you get cycles and a core you
can't extract.

```dart
// Bad: lib/core/network/auth_interceptor.dart
import '../../features/auth/data/auth_repository_impl.dart';
```

```dart
// Good: core owns the abstraction, the feature implements it
// lib/core/network/token_source.dart
abstract interface class TokenSource {
  Future<String?> currentToken();
}
// lib/features/auth/data/auth_repository_impl.dart
final class AuthRepositoryImpl implements AuthRepository, TokenSource { /* ... */ }
// lib/app/di.dart binds TokenSource to AuthRepositoryImpl
```

**Fix.** Invert the dependency with an interface in core, or move the shared
piece into core.
**False positives.** None in the code itself; but `app/`, `di/` and `router/`
are the composition root, not core, and may import features.

### ARCH-014 cross-feature-internal-import

**Low** · applies: feature-first, hybrid · doesn't apply: imports of another
feature's `domain/` · detect: arch_check (import)

**Problem.** `features/a/**` imports `features/b/data/**` or
`features/b/presentation/**`.
**Why.** Feature B's internals become feature A's API; refactoring B breaks A.
A feature's `domain/` is its public surface.

```dart
// Bad: features/checkout/presentation/view/checkout_view.dart
import '../../../cart/data/models/cart_response.dart';
```

```dart
// Good
import '../../../cart/domain/entities/cart.dart';
import '../../../cart/domain/usecases/get_cart.dart';
```

**Fix.** Depend on the other feature's entities, contracts or use cases.
Shared widgets go to `core/`.
**False positives.** App-wide session state (the signed-in user) watched by many
features. Consider moving it to `core/` or exposing it through a domain
contract; until then, Info is enough.

### ARCH-015 feature-cycle

**Medium** · applies: feature-first, hybrid · detect: arch_check (feature
graph), reported once per cycle as `a → b → a`

**Problem.** Feature imports form a cycle.
**Why.** Neither feature can be built, tested, or split into a package without
the other. Cycles grow; they rarely shrink by themselves.

```dart
// Bad
// features/cart/...      import '../../checkout/domain/usecases/start_checkout.dart';
// features/checkout/...  import '../../cart/domain/entities/cart.dart';
```

```dart
// Good: the shared concept moves down, the dependency becomes one-way
// core/commerce/line_item.dart     (shared entity)
// features/checkout/...  imports core/commerce + cart/domain
// features/cart/...      navigates to checkout by route name, no import
```

**Fix.** Extract the shared type to `core/` or a third feature, replace a
direct call with navigation by route, or invert with an interface.
**False positives.** Imports only through the composition root don't create a
feature cycle; if the checker reports one, check for barrel files re-exporting
across features.
**As calibrated.** The checker reports **one finding per strongly connected
component** of the feature graph, not one per elementary cycle (16 cycles among
8 features are one finding). The evidence is the shortest cycle, and the note
names every feature in the component. A component that exists only through
navigation (a page importing another feature's page) or through another
feature's public `models/` is **low**: route by name to break it when it hurts.
The bloclibrary layout `lib/<feature>/{bloc,view,models}` counts as features.

### AP-feature-envy-across-features

**Low** · applies: feature-first, hybrid · detect: reading (counterpart of ARCH-014)

**Problem.** A feature does another feature's work: recomputes cart totals in
checkout, re-parses another feature's JSON, duplicates its validation.
**Why.** The rule now lives in two places and drifts. It often starts as a
"quick" import of another feature's data layer.

```dart
// Bad: features/checkout/presentation/notifier/checkout_notifier.dart
final total = cart.items.fold(0.0, (s, i) => s + i.price * i.qty) * 1.15; // cart's rule, copied
```

```dart
// Good: cart owns the rule; checkout asks for it
final total = cart.totalWithTax; // getter on the Cart entity, or a cart use case
```

**Fix.** Move the behaviour to the owning feature's domain and call it.
**False positives.** Genuinely different rules that look alike (a display
estimate vs the billed amount). Ask before merging them.

### AP-context-passed-down-to-data

**High** · applies: all · detect: reading

**Problem.** A `BuildContext` is passed into a repository, service, use case or
source, to show a dialog, read the locale or theme, or navigate.
**Why.** The data layer now depends on the widget tree, can't be unit-tested,
and may use a context whose widget has been disposed after an `await`, which
throws or targets the wrong screen.

```dart
// Bad
Future<User> login(BuildContext context, String email, String pw) async {
  final res = await _api.login(email, pw);
  if (res.statusCode == 401) {
    showDialog(context: context, builder: (_) => const BadPasswordDialog());
  }
  return User.fromJson(res.data);
}
```

```dart
// Good
Future<Result<User>> login(String email, String pw) async {
  // ... return Result.error(const InvalidCredentials()) on 401
}
// the view reacts to the failure (ref.listen / BlocListener / command listener)
```

**Fix.** Pass plain values (`Locale`, `String`), return a typed failure, and let
the UI decide what to show.
**False positives.** None in data/domain. In logic classes see ARCH-102.
