# The repository pattern (and services)

Sources: Martin Fowler, *Patterns of Enterprise Application Architecture*
("Repository", by Edward Hieatt and Rob Mee); the Flutter architecture guide
and case study (repositories and services); bloclibrary.dev (repositories and
data providers). Every Flutter pattern in this skill uses repositories, and
they all agree on the core rules below.

## Contents

1. What it is
2. Roles: repository, service / source / data provider
3. Allowed dependencies
4. Rules every pattern shares
5. Where the patterns differ
6. Errors, caching and streams
7. Abstract repositories, fakes and DI
8. Anti-patterns
9. A good example
10. Reviewing repositories

## 1. What it is

Fowler: a repository "mediates between the domain and data mapping layers using
a collection-like interface for accessing domain objects". Callers ask for
domain objects; the repository hides where they come from and how they're
stored.

The Flutter guide adds that repositories are the **source of truth** for model
data: they poll services, transform raw data into **domain models**, and own the
business logic around data: caching, error handling, retry, refreshing, polling,
and refreshing on user actions. Because they're the single source of truth,
they're also the right home for app-wide session state (the signed-in user,
in-memory caches) shared by many view models.

## 2. Roles: repository, service / source / data provider

The layer below the repository has three names for one idea:

| Pattern | Name | Rule |
|---|---|---|
| Flutter MVVM | **service** | Wraps one external API (REST endpoint, platform API, local files). Stateless, no side effects beyond the call, exposes `Future`/`Stream`. One service class per data source |
| MVN / Clean Architecture | **source** / **data source** | Isolates the transport (REST, database, cache) behind a small interface. A leaf: never touches UI state |
| Bloc | **data provider** | Provides raw data; generic and versatile; simple CRUD APIs |

They all return raw or API models (DTOs). The repository turns them into domain
models.

## 3. Allowed dependencies

| From ↓ may use → | View | Logic (VM / notifier / bloc) | Use case | Repository | Service / source | DTO |
|---|---|---|---|---|---|---|
| **Repository** | no | never knows them | no | **never another repository** | yes, many (private fields) | yes |
| **Service / source** | no | no | no | never | no (leaf) | yes |

Relationships (Flutter guide): repositories ↔ view models many-to-many;
repositories ↔ services many-to-many; a service never knows a repository.

## 4. Rules every pattern shares

- **One repository per type of data** (`UserRepository`, `BookingRepository`),
  not one per screen and not one per endpoint.
- **Repositories never know about each other** (ARCH-011). When logic needs
  data from two repositories, combine it in the logic layer or a use case.
  Bloc says the same about siblings in one layer.
- **Output domain models**, not DTOs, `Response` objects or JSON maps
  (ARCH-107, `AP-leaky-repository`).
- **Keep services private.** "It's important that the service is a private
  member, so that the UI layer can't bypass the repository and call a service
  directly." The same goes for repositories inside a view model.
- **Own data concerns**: caching, retry, error mapping, offline sync,
  refresh. Those don't belong in widgets or view models.
- **The only place a data type is mutated.** Other layers ask the repository
  to change data; they never modify a shared model in place
  (`AP-two-sources-of-truth`, `AP-shared-mutable-model`).

## 5. Where the patterns differ

| Question | Flutter MVVM | MVN | Bloc | Clean Architecture |
|---|---|---|---|---|
| Who calls the repository? | view models directly, plus optional use cases | **only use cases** | blocs directly | use cases (strict) or logic (lenient) |
| Where's the contract? | `data/repositories/<type>/<type>_repository.dart` (abstract class) | `domain/repositories/` | the repository package | `domain/repositories/` |
| Name of the impl | `BookingRepositoryRemote`, `BookingRepositoryLocal` | `<Feature>RepositoryImpl` | `TodosRepository` (often concrete over an abstract API) | `<X>RepositoryImpl` |
| Error style in sources | `Result<T>` recommended | exceptions, caught in the notifier | exceptions or results | `Either`/`Result`/domain exceptions |
| Abstract repository required? | Strong recommendation | yes (`abstract interface class`) | not required; the data provider is often the abstraction | yes |

Bloc's tutorials often keep the repository concrete and put the abstraction one
level down, at the API (`TodosApi` with `LocalStorageTodosApi`). Fakes then
replace the API. That satisfies the intent of ARCH-108; read before flagging.

## 6. Errors, caching and streams

- **Map errors at the boundary.** A repository catches `DioException`,
  `SocketException`, `FirebaseException`, `FormatException` and returns a
  domain failure (`Result.error(NetworkFailure(...))`) or throws a domain
  exception. Callers above shouldn't need to import the transport package to
  handle a failure.
- **Caching** lives here. A simple in-memory cache is a private field
  (`List<Destination>? _cachedDestinations` in Compass). Invalidate it in the
  same class that mutates the data.
- **Reactive repositories** expose `Stream<T>` (Flutter: `UserProfileRepository`
  exposing `Stream<UserProfile?>`; Bloc: a todos stream several blocs
  subscribe to). This is Bloc's sanctioned way for two blocs to stay in sync
  without knowing each other.
- **Retry and polling** are repository concerns; the logic layer decides *when*
  (user pull-to-refresh), the repository decides *how*.

## 7. Abstract repositories, fakes and DI

The Flutter team rates abstract repositories **Strong**: an abstract base lets
you swap development, staging and fake implementations
(`BookingRepositoryRemote` / `BookingRepositoryLocal`). Use
`abstract interface class` when the contract has no shared implementation.

```dart
abstract interface class SessionRepository {
  Stream<User?> watchCurrentUser();
  Future<Result<void>> signOut();
}

final class FakeSessionRepository implements SessionRepository {
  final _users = StreamController<User?>.broadcast();

  void emit(User? user) => _users.add(user); // test hook

  @override
  Stream<User?> watchCurrentUser() => _users.stream;

  @override
  Future<Result<void>> signOut() async {
    _users.add(null);
    return const Result.ok(null);
  }
}
```

Register the abstract type in the composition root (`Provider<SessionRepository>`,
a `@riverpod SessionRepository sessionRepository(Ref ref)`, `RepositoryProvider<SessionRepository>`,
`getIt.registerLazySingleton<SessionRepository>(…)`), so consumers never see the
implementation.

An interface with one implementation and no fake is ceremony
(`AP-interface-for-everything`, Info), unless the project's pattern mandates
the contract (MVN, Clean Architecture) or a second implementation is planned.

## 8. Anti-patterns

| ID | Problem |
|---|---|
| ARCH-011 | Repository imports another repository |
| ARCH-107, `AP-leaky-repository` | Public methods return `Response`, `Map<String, dynamic>`, `*Dto`/`*Response`/`*Request` |
| ARCH-108 | Concrete repository with no abstraction (clean, MVN, MVVM) |
| ARCH-004 | Repository imports presentation |
| ARCH-005, ARCH-007 | Views or logic reach past the repository to a service/source |
| `AP-exceptions-across-layers` | Transport exceptions escape the repository |
| `AP-hardcoded-config-in-sources` | Base URLs, keys, timeouts hard-coded in services |
| `AP-context-passed-down-to-data` | `BuildContext` passed into a repository or service |
| `AP-singleton-abuse` | `ApiClient.instance` reached from everywhere instead of injected |
| `AP-viewmodel-exposes-repository` | Logic exposes its repository publicly, letting views bypass it |

## 9. A good example

```dart
// data/services/api/user_api_service.dart (stateless, one per data source)
final class UserApiService {
  const UserApiService(this._dio); // configured Dio injected: base URL comes from config
  final Dio _dio;

  Future<UserDto> fetchMe() async {
    final res = await _dio.get<Map<String, dynamic>>('/me');
    return UserDto.fromJson(res.data!);
  }
}

// data/repositories/user_repository.dart (the contract)
abstract interface class UserRepository {
  Future<Result<User>> getMe({bool refresh = false});
}

// data/repositories/user_repository_remote.dart
final class UserRepositoryRemote implements UserRepository {
  UserRepositoryRemote({required UserApiService api}) : _api = api;

  final UserApiService _api; // private: nobody can bypass the repository
  User? _cached;

  @override
  Future<Result<User>> getMe({bool refresh = false}) async {
    final cached = _cached;
    if (!refresh && cached != null) return Result.ok(cached);
    try {
      final user = (await _api.fetchMe()).toDomain();
      _cached = user;
      return Result.ok(user);
    } on DioException catch (e) {
      return Result.error(NetworkFailure.from(e));
    } on FormatException catch (e) {
      return Result.error(BadDataFailure(e.message));
    }
  }
}
```

## 10. Reviewing repositories

- [ ] One repository per data type; names say which type.
- [ ] No repository imports another repository or anything in presentation.
- [ ] Public methods return domain models (or `Result`/`Stream` of them).
- [ ] Services/sources are private fields, stateless, one per data source, and
      receive configuration instead of hard-coding it.
- [ ] Transport errors are caught and mapped here.
- [ ] Caching, retry and refresh live here, not in widgets or logic.
- [ ] The repository is abstract (or its data source is), and a fake exists for
      tests, where the pattern expects one.
- [ ] Logic classes hold repositories as private fields.
