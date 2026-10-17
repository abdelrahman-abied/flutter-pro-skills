# Anti-patterns: State

How state is modelled and owned: immutable state classes, ephemeral versus app state, one-time events, contradictory flags, `null` as loading, DTOs as UI state, duplicated or shared mutable state, and wildcards that hide unhandled cases.

Part of the architecture anti-pattern catalog. The index, [`references/anti-patterns.md`](../anti-patterns.md), holds the severity scale, the profile rules and a table of every ID; read it first.

## Contents

- [ARCH-106 mutable-state-class](#arch-106-mutable-state-class)
- [ARCH-109 ephemeral-state-in-provider](#arch-109-ephemeral-state-in-provider)
- [ARCH-111 event-flag-in-state](#arch-111-event-flag-in-state)
- [AP-boolean-soup-state](#ap-boolean-soup-state)
- [AP-null-as-loading](#ap-null-as-loading)
- [AP-dto-as-ui-state](#ap-dto-as-ui-state)
- [AP-two-sources-of-truth](#ap-two-sources-of-truth)
- [AP-shared-mutable-model](#ap-shared-mutable-model)
- [AP-default-hides-missing-state](#ap-default-hides-missing-state)

### ARCH-106 mutable-state-class

**Medium** · applies: mvn, bloc, riverpod, mvvm · doesn't apply: Flutter
`State<…>` subclasses; mvc, getx, provider, setstate profiles · detect:
arch_check (regex in `state`-role files)

**Problem.** A state class declares a non-`final` instance field.
**Why.** UI state should be an immutable snapshot. Mutating it in place means
listeners aren't notified, `==`-based de-duplication (Bloc skips equal states;
`select` compares) hides the change, and the UI goes stale.

```dart
// Bad
class CartState {
  List<Item> items = [];
  bool loading = false;
}
// cubit: state.items.add(item); emit(state);  → same instance, no rebuild
```

```dart
// Good
final class CartState extends Equatable {
  const CartState({this.items = const [], this.status = CartStatus.initial});
  final List<Item> items;
  final CartStatus status;
  CartState copyWith({List<Item>? items, CartStatus? status}) =>
      CartState(items: items ?? this.items, status: status ?? this.status);
  @override
  List<Object> get props => [items, status];
}
// emit(state.copyWith(items: [...state.items, item]));
```

**Fix.** Make fields `final`, add `copyWith` and value equality (`freezed`,
`equatable`, or manual), and emit new instances.
**False positives.** A `*_state.dart` file that holds a Flutter `State`
subclass, or a mutable builder used locally inside one method.

### ARCH-109 ephemeral-state-in-provider

**Low** · applies: riverpod, mvn, provider · doesn't apply: getx (controllers
own text controllers idiomatically), bloc, mvvm · detect: arch_check (regex)

**Problem.** A logic file or provider declaration constructs a
`TextEditingController`, `ScrollController`, `FocusNode`, `PageController` or
`TabController`.
**Why.** riverpod.dev: AVOID providers for ephemeral state. These objects are
route-scoped and tied to widgets; held in a provider they survive navigation
(the back button shows stale text or scroll position), and they often aren't
disposed.

```dart
// Bad
@riverpod
class SearchNotifier extends _$SearchNotifier {
  final queryController = TextEditingController();
  @override
  SearchState build() => const SearchIdle();
}
```

```dart
// Good
class SearchView extends HookConsumerWidget {
  const SearchView({super.key});
  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final query = useTextEditingController(); // or a State field disposed in dispose()
    return TextField(
      controller: query,
      onSubmitted: ref.read(searchNotifierProvider.notifier).search,
    );
  }
}
```

**Fix.** Keep controllers in the widget (`State` or hooks); send values to the
notifier.
**False positives.** A provider that only *references* a controller type in a
signature, or an app-wide controller deliberately shared (rare; document it).

### ARCH-111 event-flag-in-state

**Low** · applies: mvn, bloc, mvvm, riverpod · detect: arch_check (regex on `bool`
fields in state files, named like one-time events: `should(Show|Navigate|Pop|Open)*`,
`navigate*`, `pop*`, `open*(Dialog|Sheet)`, `show*(Snackbar|Toast|Dialog|Sheet|Error|Message)`,
`is*Shown`. Bare toggles such as `showPassword` and `isExpanded` are deliberately not matched)

**Problem.** A one-time event (show a dialog, navigate, pop) is modelled as a
persistent `bool` in state.
**Why.** The flag must be reset after acting on it. If it isn't, the dialog
reappears on the next rebuild or on rotation; if it is, there's a reset race.
MVN's spec: "Never store transient events as mutable booleans in the state
class."

```dart
// Bad
final class ProfileState {
  const ProfileState({this.user, this.showSavedDialog = false});
  final User? user;
  final bool showSavedDialog;
}
```

```dart
// Good (MVN/Riverpod: ref.listen; Bloc: BlocListener; MVVM: command listener)
ref.listen(profileNotifierProvider, (prev, next) {
  if (prev is ProfileSaving && next is ProfileSaved) {
    showDialog<void>(context: context, builder: (_) => const SavedDialog());
  }
});
```

**Fix.** React to a state *transition* in a listener, or expose a stream of
one-off effects from the logic class.
**False positives.** Persistent UI toggles are real state, not events:
`showPassword`, `showArchived`, `isFilterPanelShown` that stays open until the
user closes it. Flag only flags that the code resets right after acting on them.
**As calibrated.** The rule scans `state`-role files only. A `*_state.dart`
file whose class extends or mixes in `ChangeNotifier`/`ValueNotifier` is
classified as `logic` (content beats the file name), so its fields are neither
ARCH-106 nor ARCH-111. Judge a `bool` there the same way by reading: a flag the
notifier sets and the view resets is still an event.

### AP-boolean-soup-state

**Medium** · applies: all · doesn't apply: Bloc's single class + status enum
(a sanctioned shape) · detect: reading

**Problem.** State is a cluster of independent fields (`isLoading`, `hasError`,
`errorMessage`, `data`, `isEmpty`) that can contradict each other.
**Why.** `isLoading && errorMessage != null` is representable, so somewhere it
happens: a spinner over an error, stale data shown as fresh. Every reader must
check the fields in the right order.

```dart
// Bad
class OrdersViewModel extends ChangeNotifier {
  bool isLoading = false;
  String? error;
  List<Order>? orders;
  bool isRefreshing = false;
}
```

```dart
// Good
sealed class OrdersState { const OrdersState(); }
final class OrdersLoading extends OrdersState { const OrdersLoading(); }
final class OrdersLoaded extends OrdersState {
  const OrdersLoaded(this.orders, {this.refreshing = false});
  final List<Order> orders;
  final bool refreshing; // only meaningful when loaded
}
final class OrdersFailed extends OrdersState {
  const OrdersFailed(this.message);
  final String message;
}
```

**Fix.** A sealed hierarchy, `AsyncValue` (Riverpod), a `Command` per action
(MVVM), or a single class with a status enum (Bloc).
**False positives.** Genuinely independent flags (`isOffline` alongside
loaded data) aren't soup. The test: can two of them be true at once and still
make sense?

### AP-null-as-loading

**Medium** · applies: all · detect: reading

**Problem.** `null` stands for "not loaded yet", and also, implicitly, "failed"
or "doesn't exist".
**Why.** The UI can't tell loading from empty from error, so it shows an
endless spinner on failure or "No profile" while loading.

```dart
// Bad
User? user; // null: loading? not signed in? request failed?
Widget build(BuildContext context) =>
    user == null ? const CircularProgressIndicator() : ProfileCard(user: user!);
```

```dart
// Good (Riverpod)
final profile = ref.watch(profileProvider); // AsyncValue<User?>
return switch (profile) {
  AsyncData(value: final user?) => ProfileCard(user: user),
  AsyncData() => const SignInPrompt(),
  AsyncError(:final error) => ErrorView(message: '$error'),
  AsyncLoading() => const CircularProgressIndicator(),
};
```

**Fix.** Model loading and failure explicitly: sealed state, `AsyncValue`,
`AsyncSnapshot`, a `Command`'s `running`/`error`.
**False positives.** A nullable field inside an already-loaded state where
`null` has one documented meaning ("no avatar").

### AP-dto-as-ui-state

**Medium** (small MVVM apps without separate API models: **Low**) · applies:
all · detect: reading (ARCH-006 catches the imports)

**Problem.** UI state holds transport models: JSON-shaped classes, nullable
everything, snake_case fields, server enums as strings.
**Why.** Every API change reaches widgets, and widgets end up doing parsing
and null-patching.

```dart
// Bad
final class MovieSuccess extends MovieState {
  const MovieSuccess(this.movies);
  final List<MovieResponse> movies; // release_date: String?, vote_average: dynamic
}
```

```dart
// Good
final class MovieSuccess extends MovieState {
  const MovieSuccess(this.movies);
  final List<MovieEntity> movies; // releaseDate: DateTime, rating: double
}
```

**Fix.** Map in the repository (`toEntity()`/`toDomain()`); state holds domain
models or purpose-built UI models.
**False positives.** In apps where the Flutter guide's "separate API and domain
models" (Conditional: large apps) wasn't adopted, a single clean model class
is fine.

### AP-two-sources-of-truth

**High** · applies: all · detect: reading

**Problem.** The same data is held and updated in two places: two view models
each caching the cart, a widget copying provider state into its own field, a
repository plus a global variable.
**Why.** They drift. The badge says 3 items, the cart shows 2. The Flutter
guide's single-source-of-truth rule: the repository is the only class that
mutates a type of data; everything else derives.

```dart
// Bad
class _CartBadgeState extends State<CartBadge> {
  late int _count = widget.initialCount; // copied once, updated by hand elsewhere
}
```

```dart
// Good
class CartBadge extends ConsumerWidget {
  const CartBadge({super.key});
  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final count = ref.watch(cartNotifierProvider.select((s) => s.itemCount));
    return Badge(label: Text('$count'));
  }
}
```

**Fix.** Keep one owner (a repository, exposed via stream/provider); derive
everything else with getters, `select`, or by watching it.
**False positives.** A form's draft copy of data being edited is deliberate
ephemeral state until saved.

### AP-shared-mutable-model

**Medium** · applies: all · detect: reading

**Problem.** Models with mutable fields, or mutable collections exposed
publicly, are passed between screens and changed in place.
**Why.** One screen's change silently alters another's data without
notification; equality and caching break; bugs depend on navigation order.

```dart
// Bad
class Booking { String title; List<Guest> guests; Booking(this.title, this.guests); }
class HomeViewModel extends ChangeNotifier {
  List<Booking> bookings = []; // the view can bookings.add(...) without notifyListeners
}
```

```dart
// Good
@freezed
abstract class Booking with _$Booking {
  const factory Booking({required String title, required List<Guest> guests}) = _Booking;
}
class HomeViewModel extends ChangeNotifier {
  List<Booking> _bookings = const [];
  UnmodifiableListView<Booking> get bookings => UnmodifiableListView(_bookings);
}
```

**Fix.** Immutable models (`final` fields, `copyWith`, `freezed`); expose
collections read-only; mutate through the repository.
**False positives.** Builders or form drafts that never escape one widget.

### AP-default-hides-missing-state

**Low** · applies: all · detect: reading

**Problem.** A `switch` over a sealed state uses `default:` or `_ =>`, so a new
state variant compiles and silently falls into the fallback.
**Why.** Exhaustiveness checking is the main reason to use a sealed state. The
MVN spec: "no `default` clause that hides a missing state".

```dart
// Bad
return switch (state) {
  MovieSuccess(:final movies) => MovieList(movies: movies),
  _ => const SizedBox.shrink(), // MovieError added later shows a blank screen
};
```

```dart
// Good
return switch (state) {
  MovieInitial() => const StartPrompt(),
  MovieLoading() => const Center(child: CircularProgressIndicator()),
  MovieError(:final message) => ErrorView(message: message),
  MovieSuccess(:final movies) => MovieList(movies: movies),
};
```

**Fix.** List every variant; group with `||` patterns when several render the
same.
**False positives.** Status *enums* with non-exclusive states (Bloc's single
class), and switches over open types (`int`, `String`) need a fallback.
