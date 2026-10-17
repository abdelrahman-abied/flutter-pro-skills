# Anti-patterns: Over-engineering

Structure that costs more than it buys: use cases that only forward, a domain layer the app doesn't need yet, interfaces nobody fakes, and entities that are either empty shells (their rules duplicated elsewhere) or doing I/O.

Part of the architecture anti-pattern catalog. The index, [`references/anti-patterns.md`](../anti-patterns.md), holds the severity scale, the profile rules and a table of every ID; read it first.

These are **Info** by default: trade-offs, not defects. Report them when the
ceremony is visibly costing the team (slow changes, boilerplate-only diffs), and
never when the project or its pattern mandates the structure.

### AP-passthrough-usecase

**Info** · applies: mvvm, bloc, clean_architecture (lenient), riverpod,
provider · doesn't apply: **mvn** (one use case per intent is prescribed, even
when it only forwards), or any project whose instructions mandate use cases ·
detect: reading

**Problem.** A use case whose `call()` only forwards to one repository method.
**Why.** The Flutter guide: creating a use case for every data access
"intensifies" the cons, "a significant amount of unnecessary overhead"; add use
cases "only when needed": logic that merges repositories, is complex, or is
reused.

```dart
// Ceremony (outside MVN)
final class GetUser {
  const GetUser(this._repo);
  final UserRepository _repo;
  Future<User> call() => _repo.getUser();
}
```

```dart
// Simpler in MVVM/Bloc: the logic class uses the repository directly
final class ProfileViewModel extends ChangeNotifier {
  ProfileViewModel({required UserRepository users}) : _users = users;
  final UserRepository _users;
}
```

**Fix.** Optional: inline it, or keep it if the team values uniformity.
**False positives.** Use cases that are a deliberate seam for an upcoming rule,
or that exist so the rest of a feature follows one shape. Under MVN, never.

### AP-premature-domain-layer

**Info** · applies: all · doesn't apply: projects that declare Clean
Architecture or MVN · detect: reading

**Problem.** A small app (a few screens, CRUD over one API) has full
domain/data/presentation layering per feature: entities identical to DTOs,
mapper classes, use cases, contracts and impls for everything.
**Why.** The Flutter guide calls the domain layer optional, and lists its cons:
"increases complexity … higher cognitive load", "additional mocks",
"boilerplate". Many apps "might not need this optional layer".

```dart
// Ceremony: a 3-screen app
// features/settings/domain/{entities,repositories,usecases}/  data/{models,sources,repositories}/
// SettingsEntity == SettingsModel field for field; GetSettings forwards to SettingsRepository
```

```dart
// Proportionate
// ui/settings/{settings_screen.dart, settings_viewmodel.dart}
// data/repositories/settings_repository.dart  data/services/prefs_service.dart
```

**Fix.** Suggest the lighter layout for new code; don't demand a rewrite of
working code.
**False positives.** Apps expected to grow, or teams standardising across many
apps.

### AP-interface-for-everything

**Info** · applies: all · doesn't apply: repository contracts under mvn and
clean_architecture (mandated), and any type with a fake in tests or a second
implementation · detect: reading

**Problem.** Every class has an abstract twin (`IFooService` / `FooServiceImpl`)
with exactly one implementation and no fake.
**Why.** An interface pays for itself when something substitutes it: a fake, a
second backend, a platform split. Without that it doubles the files and adds a
jump-to-definition hop.

```dart
// Ceremony
abstract interface class DateFormatterService { String format(DateTime d); }
final class DateFormatterServiceImpl implements DateFormatterService { /* ... */ }
```

```dart
// Simpler
final class DateFormatter {
  const DateFormatter(this._locale);
  final String _locale;
  String format(DateTime d) => DateFormat.yMMMd(_locale).format(d);
}
```

**Fix.** Keep interfaces at real seams (repositories, services wrapping I/O,
platform code). Dart classes are implicit interfaces, so a test can still
`implements DateFormatter` later.
**False positives.** The `I` prefix is a naming issue for the `dart-naming`
skill, not this one.

### AP-anemic-vs-fat-entity

**Info** · applies: clean_architecture, mvn · detect: reading

**Problem.** Two opposite failures. *Anemic*: entities are bags of fields while
the same business rule (is the order cancellable? the total with tax?) is
re-implemented in several view models or widgets. *Fat*: entities do I/O, JSON,
formatting or hold framework types.
**Why.** Anemic entities are **fine in Flutter** when the rules live on the
server and the client only displays data. They become a problem when rules are
duplicated on the client. Fat entities violate the dependency rule (see
ARCH-003).

```dart
// Duplicated rule (in two notifiers)
final canCancel = order.status == 'placed' && DateTime.now().difference(order.placedAt).inHours < 24;
```

```dart
// One home for it
@immutable
final class Order {
  const Order({required this.status, required this.placedAt});
  final OrderStatus status;
  final DateTime placedAt;
  bool canCancelAt(DateTime now) =>
      status == OrderStatus.placed && now.difference(placedAt) < const Duration(hours: 24);
}
```

**Fix.** Move a rule into the entity (pure, no I/O) or a use case once it's
needed twice; move I/O and JSON out of entities.
**False positives.** Display-only apps with no client-side rules: anemic is
correct.
