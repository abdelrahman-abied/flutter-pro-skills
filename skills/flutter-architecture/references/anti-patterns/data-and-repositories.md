# Anti-patterns: Data and repositories

The data layer's contract with the rest of the app: logic depending on concrete data types, repositories that depend on each other or leak transport types and errors, single concrete repositories with no contract, and configuration hard-coded in sources.

Part of the architecture anti-pattern catalog. The index, [`references/anti-patterns.md`](../anti-patterns.md), holds the severity scale, the profile rules and a table of every ID; read it first.

### ARCH-007 logic-depends-on-concrete-data

**Medium** · applies: all · doesn't apply: importing an abstract repository
contract · detect: arch_check (import)

**Problem.** A logic class imports a source, service, repository
implementation, or an I/O package.
**Why.** The logic can't be tested with a fake, and transport details leak
into presentation. (Under MVN, importing even the contract is ARCH-012.)

```dart
// Bad
import 'package:dio/dio.dart';
import '../../data/repositories/user_repository_impl.dart';
class ProfileCubit extends Cubit<ProfileState> {
  ProfileCubit() : _repo = UserRepositoryImpl(Dio()), super(const ProfileInitial());
  final UserRepositoryImpl _repo;
}
```

```dart
// Good
import '../../domain/repositories/user_repository.dart';
class ProfileCubit extends Cubit<ProfileState> {
  ProfileCubit({required UserRepository users}) : _users = users, super(const ProfileInitial());
  final UserRepository _users;
}
```

**Fix.** Depend on the contract; construct implementations in the composition
root.
**False positives.** Layer-first apps where the repository *is* concrete and
lives in `repositories/` (see ARCH-108); the import is then expected. Report
ARCH-108 instead of both.
**As calibrated (what the checker does).**
- A concrete `*Repository` with no contract anywhere has role `repository`, and
  ARCH-007 skips it: Bloc and the Flutter guide use concrete repositories
  injected through the constructor (bloc.md section 3, repository-pattern.md
  section 5).
- When a contract and its implementation share a file, only references to the
  implementation count.
- An I/O package imported only for `CancelToken` (or another value type) doesn't
  count; exception types only (`DioException`) don't either.
- Under **riverpod** and **provider** the logic reaches data through providers
  or `context.read`, so ARCH-007 fires only on direct construction
  (`XRepositoryImpl()`, `XService()`, `Dio(`) or on an actual I/O call in a logic
  class (`_dio.get(`, `http.post(`, `SharedPreferences.getInstance(`,
  `FirebaseFirestore.instance`, `Supabase.instance`, `Socket.connect(` ...).
- Under **mvn**, when ARCH-012 fires on the same import, only ARCH-012 is
  reported (note `also ARCH-007`).

### ARCH-011 repository-depends-on-repository

**Medium** · applies: all · doesn't apply: an impl importing its own contract
(same stem without `_impl`) · detect: arch_check (import)

**As calibrated.** The importer must declare a `*Repository` class itself (a
barrel or a `*Factory`/`*Module`/`*Locator` that only constructs repositories is
not a repository: roles `barrel` and `di`). `export` edges don't count (a package
barrel `lib/<pkg>.dart` re-exporting `src/x_repository.dart`). References only in
`extends`/`with`/`implements` clauses (a shared `ApiRepository` base), static
helpers (`EntriesRepository.entriesPath()`), and providers whose value isn't a
`*Repository` don't count.

**Problem.** A repository imports another repository.
**Why.** The Flutter guide: "Repositories should never be aware of each
other." Coupled repositories form hidden dependency chains and cycles, and
caching/invalidation becomes order-dependent.

```dart
// Bad
final class OrderRepositoryImpl implements OrderRepository {
  OrderRepositoryImpl(this._api, this._users);
  final OrderApi _api;
  final UserRepository _users; // to attach the user to each order
}
```

```dart
// Good: combine in the logic layer or a use case
final class GetOrdersWithUser {
  const GetOrdersWithUser(this._orders, this._users);
  final OrderRepository _orders;
  final UserRepository _users;
  Future<(User, List<Order>)> call() async =>
      (await _users.me(), await _orders.list());
}
```

**Fix.** Merge data in the view model / notifier / bloc or a use case; share
lower-level *services* between repositories instead.
**False positives.** Two repositories sharing a *service* (an `ApiClient`) is
fine and expected.

### ARCH-107 repository-leaks-transport

**Medium** · applies: `repository_pattern: true` · detect: arch_check (regex on
public method return types)

**Problem.** A repository's public method returns `Response<…>`,
`http.Response`, `Map<String, dynamic>`, or a type ending in
`Dto`/`Response`/`Request`.
**Why.** Repositories exist to output domain models. Returning transport
types pushes parsing and status-code handling into logic and UI.

```dart
// Bad
abstract interface class WeatherRepository {
  Future<Response<dynamic>> current(String city);
}
```

```dart
// Good
abstract interface class WeatherRepository {
  Future<Result<Weather>> current(String city);
}
```

**Fix.** Parse and map inside the repository; return entities/domain models.
**False positives.** A domain type that happens to end in `Response`
(`SurveyResponse` as a business concept). Rename it or suppress with a reason.

### ARCH-108 concrete-repository-only

**Low** · applies: clean_architecture, mvn, mvvm · detect: arch_check (no
abstract/interface/sealed `XRepository` anywhere in `lib/`)

**Problem.** `class XRepository` is concrete and has no abstraction.
**Why.** The Flutter team rates abstract repositories Strong: they let you swap
development, staging and fake implementations. MVN and Clean Architecture
require the contract in `domain/`.

```dart
// Bad
class BookingRepository {
  BookingRepository(this._api);
  final ApiClient _api;
}
```

```dart
// Good
abstract interface class BookingRepository {
  Future<Result<List<BookingSummary>>> getBookingsList();
}
final class BookingRepositoryRemote implements BookingRepository { /* ... */ }
final class BookingRepositoryLocal implements BookingRepository { /* ... */ }
```

**Fix.** Extract an `abstract interface class` and bind the implementation in
DI.
**False positives.** Bloc-style apps that abstract one level lower (a
`TodosApi` interface under a concrete `TodosRepository`) already have the
seam. Tiny apps without tests: Info at most (`AP-interface-for-everything`).

### AP-leaky-repository

**Medium** · applies: all · detect: reading (ARCH-107 catches return types)

**Problem.** The repository's contract exposes its implementation: transport
exceptions (`DioException`), status codes, Firestore `DocumentSnapshot`s,
pagination cursors from the API, query builders, cache internals.
**Why.** Callers become coupled to the backend; switching from REST to
Firestore, or adding a cache, changes every caller.

```dart
// Bad
abstract interface class PostRepository {
  Future<QuerySnapshot<Map<String, dynamic>>> page(DocumentSnapshot? after);
}
```

```dart
// Good
abstract interface class PostRepository {
  Future<Result<Page<Post>>> page({PageToken? after}); // PageToken: opaque domain type
}
```

**Fix.** Define the contract in domain terms; translate inside the
implementation.
**False positives.** None, though small apps may not need the abstraction at
all; then judge the concrete class's public API the same way.

### AP-exceptions-across-layers

**Medium** · applies: all · detect: reading

**Problem.** Transport exceptions (`DioException`, `SocketException`,
`FormatException`, `FirebaseException`) travel unmapped from services to the
UI, or are never caught.
**Why.** Dart exceptions are unchecked: callers aren't told what can throw, so
someone forgets a `try`, and the error crashes or vanishes. The Flutter guide
recommends a `Result` type to force handling ("a recommendation, but not a
requirement").

```dart
// Bad
class UserProfileViewModel extends ChangeNotifier {
  Future<void> load() async {
    _profile = await _repo.getUserProfile(); // throws HttpException: uncaught
    notifyListeners();
  }
}
```

```dart
// Good
Future<void> load() async {
  switch (await _repo.getUserProfile()) { // Future<Result<UserProfile>>
    case Ok(:final value):
      _profile = value;
    case Error(:final error):
      _error = error;
  }
  notifyListeners();
}
```

**Fix.** Catch and map at the repository boundary, and return `Result`/
`Either` or throw domain exceptions; handle every failure in the logic layer.
**False positives.** MVN's spec catches exceptions in the notifier and maps
them to an error state; that's the spec's style, not a finding, as long as they
are caught. Don't demand `Result` where the project consistently uses
exceptions *and* catches them.

### AP-hardcoded-config-in-sources

**Medium** · applies: all · detect: reading

**Problem.** Base URLs, API keys, timeouts, feature flags and environment
switches are literals inside services and sources.
**Why.** You can't point the app at staging or a fake server without editing
code, tests hit production, and keys in source end up in version control. (Any
key shipped in a client can be extracted; treat it as public.)

```dart
// Bad
class WeatherApi {
  final _dio = Dio(BaseOptions(baseUrl: 'https://api.weather.com/v2', connectTimeout: const Duration(seconds: 5)));
  static const _key = 'sk_live_abc123';
}
```

```dart
// Good
final class WeatherApi {
  const WeatherApi(this._dio); // Dio configured in the composition root from AppConfig
  final Dio _dio;
}
// main_staging.dart / main_production.dart (or --dart-define) build AppConfig
```

**Fix.** Inject a configured client or an `AppConfig`; select per flavor or
`--dart-define`; keep secrets on a server.
**False positives.** Truly fixed constants (a public CDN path, an API version
the code is written against).
