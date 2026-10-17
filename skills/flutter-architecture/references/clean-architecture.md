# Clean Architecture in Flutter

Source: Robert C. Martin, "The Clean Architecture" (2012) and *Clean
Architecture* (2017). It is a set of principles, not a Flutter API, and there is
no official Flutter guidance named "Clean Architecture". The Flutter team's
guide reaches a compatible but lighter design: an *optional* domain layer, and
view models that may call repositories directly (see `mvvm.md`). MVN applies
Clean Architecture strictly (see `mvn.md`).

Use this file whenever the profile says `clean_architecture: true`, together
with the reference for the presentation pattern.

## Contents

1. What it is
2. The four circles, mapped to Flutter
3. The dependency rule and allowed dependencies
4. Folder layouts
5. Data, errors and control flow across boundaries
6. DI and testing
7. When it is worth it
8. Pattern-specific anti-patterns
9. A good example
10. Reviewing a Clean Architecture codebase

## 1. What it is

Clean Architecture organises code in concentric layers around the business
rules, so the rules can be tested without the UI, database or network, and
those outer details can change without touching the rules. It draws on
hexagonal architecture (ports and adapters) and onion architecture, and its
one non-negotiable rule is the **dependency rule**:

> Source code dependencies can only point inwards. Nothing in an inner circle
> can know anything at all about something in an outer circle.

## 2. The four circles, mapped to Flutter

| Circle (inner → outer) | Martin's meaning | In a Flutter app |
|---|---|---|
| **Entities** | Enterprise-wide business rules; the least likely to change | `domain/entities/`: immutable business objects, value objects, pure functions on them |
| **Use cases** | Application-specific business rules; orchestrate entities; define input/output ports | `domain/usecases/` and `domain/repositories/` (the ports: abstract contracts the data layer implements) |
| **Interface adapters** | Convert data between the use cases' format and the outside's: controllers, presenters, gateways | `data/repositories/` (gateway implementations), `data/models/` (DTOs and mappers); in presentation, the bloc / notifier / view model plays controller + presenter |
| **Frameworks & drivers** | The details: UI, DB, web, devices | Flutter widgets, `dio`/`http`, `sqflite`/`drift`/`hive`, Firebase, platform channels (`data/sources/`, `presentation/view/`) |

The usual Flutter shorthand collapses this to three layers: **domain**, **data**,
**presentation**.

## 3. The dependency rule and allowed dependencies

`presentation → domain ← data`. The domain is the centre and imports nothing
from data or presentation. Data depends on domain because it *implements* the
domain's contracts (dependency inversion).

| From ↓ may import → | entities | repo contracts | use cases | DTOs/models | repo impl | sources | logic (bloc/notifier/VM) | widgets |
|---|---|---|---|---|---|---|---|---|
| **entities** | yes | no | no | no | no | no | no | no |
| **repo contracts** | yes | yes | no | no | no | no | no | no |
| **use cases** | yes | yes | yes (composition) | no | no | no | no | no |
| **DTOs/models** | yes (to map) | no | no | yes | no | no | no | no |
| **repo impl** | yes | yes (implements) | no | yes | — | yes | no | no |
| **sources** | no | no | no | yes | no | yes | no | no |
| **logic** | yes | yes (strict: no) | **yes** | no | no | no | depends on pattern | no |
| **widgets** | yes | no | no | no | no | no | yes | yes |

The "logic → repo contracts" cell is where the variants split. Strict Clean
Architecture (and MVN) routes all logic through use cases. Many Flutter Clean
Architecture apps, and the Flutter MVVM guide, let logic use a repository
contract directly when there's no business rule to put in a use case. Under the
`clean_architecture` flag alone, don't report that; report it only when the
project or its pattern (MVN: ARCH-012) requires use cases.

**Domain purity** (ARCH-003): domain files import only Dart, `package:meta`,
and pure-Dart helpers (`equatable`, `freezed_annotation`, `fpdart`/`dartz`,
`collection`). Not `package:flutter/*` (`foundation.dart` is a low finding: use
`package:meta` for `@immutable`), not I/O packages, not state-management
packages. MVN additionally allows `riverpod_annotation` in `domain/usecases/`
for the use-case provider.

## 4. Folder layouts

Feature-first, the common Flutter convention (popularised by the "Flutter TDD
Clean Architecture" course and used by MVN):

```text
lib/
├── core/                     # errors/failures, network info, Result/Either helpers, DI
└── features/<feature>/
    ├── domain/
    │   ├── entities/
    │   ├── repositories/     # abstract contracts
    │   └── usecases/
    ├── data/
    │   ├── models/           # DTOs with fromJson/toJson and toEntity()
    │   ├── datasources/      # remote / local
    │   └── repositories/     # *RepositoryImpl
    └── presentation/
        ├── bloc/ | notifier/ | view_model/
        ├── pages/ | view/
        └── widgets/
```

Layer-first is also valid: `lib/{domain,data,presentation}/<feature>/…`. It
makes the dependency rule visible at the top level but scatters a feature
across three trees. Judge consistency, not the choice.

Cross-feature rules (feature-first and hybrid layouts): `core/` must not import
features (ARCH-013); features import each other's `domain/` only, never
`data/` or `presentation/` (ARCH-014); the feature graph has no cycles
(ARCH-015).

## 5. Data, errors and control flow across boundaries

- **Entities cross inward boundaries; DTOs don't.** Repositories map DTOs to
  entities (`toEntity()`) before returning. Martin: data crossing a boundary
  should be in the form most convenient for the inner circle, never a database
  row or framework type.
- **Control flow vs dependency direction.** At runtime the use case calls "out"
  to the repository, but at compile time it depends only on the contract it
  owns. That's the dependency inversion that makes the rule hold.
- **Errors.** Transport exceptions (`DioException`, `SocketException`,
  `FirebaseException`) are details. Catch them in the data layer and map them to
  domain failures, returned as a `Result`/`Either` or thrown as domain
  exceptions. Popular choices: the Flutter team's `sealed class Result<T>`
  (`Ok`/`Error`), `fpdart`/`dartz` `Either<Failure, T>`, or plain exceptions of
  domain types. Any of them is fine; transport exceptions reaching widgets are
  not (`AP-exceptions-across-layers`, `AP-leaky-repository`).
- **Use-case shape.** One intent per class with `call()`, so the call site reads
  like a function (`await getTrending()`). A generic
  `abstract interface class UseCase<T, P> { Future<T> call(P params); }` is a
  common convention, not a requirement.

## 6. DI and testing

- Bind implementations to contracts in the **composition root**: Riverpod
  providers (MVN does this per layer), `get_it`/`injectable`, `provider`, or
  `RepositoryProvider`. Inner layers receive contracts through constructors.
- Test inward-out: entities and use cases with fakes of the repository
  contracts (no Flutter needed, plain `test`); repository impls with fake
  sources and recorded JSON; logic classes with fake use cases; widgets with
  fake logic.

## 7. When it is worth it

The Flutter guide's trade-off table applies: a domain layer avoids duplication
in view models, improves testability and readability, but increases
complexity, needs extra mocks, and adds boilerplate. Its advice is to add use
cases "only when needed": when logic merges several repositories, is very
complex, or is reused by several view models.

Signs Clean Architecture is paying off: several teams, business rules that
live on the client (pricing, eligibility, offline sync), multiple data sources
per entity, a long-lived app.

Signs it is overhead: every use case is one line forwarding to a repository,
every repository has exactly one implementation and no fake, entities and DTOs
are field-for-field identical, and the app is a handful of CRUD screens.
Report that as Info (`AP-premature-domain-layer`, `AP-passthrough-usecase`,
`AP-interface-for-everything`) unless the project or pattern (MVN) mandates the
structure.

## 8. Pattern-specific anti-patterns

| ID | Under clean_architecture |
|---|---|
| ARCH-001, ARCH-002 | Domain imports data or presentation: defeats the pattern's core guarantee (High) |
| ARCH-003 | Domain imports Flutter, I/O or state-management packages |
| ARCH-006, `AP-dto-as-ui-state` | DTOs reach presentation |
| ARCH-107, `AP-leaky-repository` | Repository contract returns `Response`, `Map<String, dynamic>` or DTO types |
| ARCH-108 | Concrete repository with no contract in `domain/` |
| ARCH-013/014/015 | Core importing features, cross-feature internals, feature cycles |
| `AP-exceptions-across-layers` | Transport exceptions escape the data layer |
| `AP-anemic-vs-fat-entity` | Business rules duplicated across view models while entities are bags of fields (Info; often fine) |
| `AP-passthrough-usecase`, `AP-premature-domain-layer`, `AP-interface-for-everything` | Ceremony without benefit (Info) |

A common shortcut, models that `extend` the entity (`class MovieModel extends
Movie`), couples the DTO shape to the entity shape but keeps the dependency
direction correct (data → domain). Treat it as a project choice, not a finding.

## 9. A good example

```dart
// features/order/domain/entities/order.dart
import 'package:meta/meta.dart';

@immutable
final class Order {
  const Order({required this.id, required this.lines});

  final String id;
  final List<OrderLine> lines;

  Money get total => lines.fold(Money.zero, (sum, l) => sum + l.subtotal);
  bool get canCheckout => lines.isNotEmpty && total > Money.zero;
}
```

```dart
// features/order/domain/repositories/order_repository.dart
abstract interface class OrderRepository {
  Future<Result<Order>> getOrder(String id);
  Future<Result<void>> submit(Order order);
}

// features/order/domain/usecases/checkout.dart
final class Checkout {
  const Checkout(this._orders, this._payments);

  final OrderRepository _orders;
  final PaymentRepository _payments; // two repositories: a real reason for a use case

  Future<Result<void>> call(String orderId) async {
    final Order order;
    switch (await _orders.getOrder(orderId)) {
      case Ok(:final value):
        order = value;
      case Error(:final error):
        return Result.error(error);
    }
    if (!order.canCheckout) return Result.error(const EmptyOrderFailure());
    return switch (await _payments.charge(order.total)) {
      Ok() => await _orders.submit(order),
      Error(:final error) => Result.error(error),
    };
  }
}
```

```dart
// features/order/data/repositories/order_repository_impl.dart
final class OrderRepositoryImpl implements OrderRepository {
  const OrderRepositoryImpl(this._api);

  final OrderApi _api; // a source in data/sources/

  @override
  Future<Result<Order>> getOrder(String id) async {
    try {
      final dto = await _api.fetchOrder(id);   // OrderDto stays in data/
      return Result.ok(dto.toEntity());
    } on DioException catch (e) {
      return Result.error(NetworkFailure.fromDio(e)); // transport error mapped here
    }
  }

  @override
  Future<Result<void>> submit(Order order) async { /* ... */ }
}
```

`EmptyOrderFailure` and `NetworkFailure` implement `Exception` and live in
`core/` or the feature's `domain/`, so the presentation layer can switch on
them without importing `dio`.

## 10. Reviewing a Clean Architecture codebase

- [ ] `domain/` imports nothing from `data/`, `presentation/`, Flutter, I/O or
      state-management packages (MVN's use-case-provider seam excepted).
- [ ] Every repository the logic layer uses has a contract in `domain/`; the
      implementation lives in `data/`.
- [ ] Repositories return entities, never DTOs, `Response` objects or raw maps.
- [ ] Transport exceptions are mapped to domain failures in the data layer.
- [ ] Use cases carry real logic, or the project/pattern mandates them; note
      pass-through ones as Info otherwise.
- [ ] DTOs never appear in presentation imports.
- [ ] Composition root binds implementations; no layer constructs its own
      dependencies from an outer layer.
- [ ] `core/` doesn't import features; features share only `domain/`; no
      feature cycles.
- [ ] Domain and use cases have plain-Dart unit tests with fakes.
