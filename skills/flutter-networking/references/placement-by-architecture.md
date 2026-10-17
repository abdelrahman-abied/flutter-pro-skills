# Placement by architecture

The API layer has the same shape in every pattern: **a remote source** wraps
the client, **the repository** maps DTOs to entities and transport errors to
failures, and **the logic holder** (use case + notifier, view model, bloc,
controller) only sees domain types. What differs is the folder, the DI style,
and the hook that ties a request's lifetime to its owner.

Detect the pattern first: run
`../flutter-architecture/scripts/arch_check.py <root> --json` or read the
project's instructions file. A declared convention wins.

## Contents

1. Who owns what
2. MVN (Riverpod codegen + Clean)
3. MVVM (Flutter architecture guide)
4. Bloc / Cubit
5. Clean Architecture (any state solution)
6. Provider, GetX, plain Riverpod
7. Lifetime hooks: cancel and close

## 1. Who owns what

| Piece | Owner | Never in |
|---|---|---|
| the configured client | composition root / core network provider | features, widgets, logic |
| one remote source per resource (`products`, `orders`) | `data/` | domain, presentation |
| DTOs, `fromJson`/`toJson` | `data/models/` (or the API package) | domain, UI state |
| DTO → entity mapping | repository (or a mapper next to the DTO, called by it) | logic, widgets |
| transport error → typed failure | repository (`flutter-error-handling`) | logic, widgets |
| request lifetime (cancel token, socket) | the logic holder that started it, through the repository | the widget tree |
| pagination state (page, cursor, hasMore, in-flight) | the logic holder | the repository (it fetches one page) |

## 2. MVN (Riverpod codegen + Clean)

```
lib/core/network/api_client.dart                  @Riverpod(keepAlive: true) Dio apiClient(Ref ref)
lib/features/catalog/data/sources/catalog_remote_source.dart
lib/features/catalog/data/models/product_dto.dart
lib/features/catalog/data/repositories/catalog_repository_impl.dart
lib/features/catalog/domain/repositories/catalog_repository.dart
lib/features/catalog/domain/usecases/load_products_usecase.dart
lib/features/catalog/presentation/notifier/catalog_notifier.dart
```

- The source takes `Dio` (or `http.Client`) in its constructor; its provider
  reads `apiClientProvider`.
- The repository impl calls the source, maps `ProductDto` → `Product`, and maps
  `DioException` to `Failure` (ERR-004 reports leaks).
- Use cases take the repository contract. Notifiers call use cases, never a
  source (ARCH-012).
- Pagination: the notifier holds `items`, `page`/`cursor`, `hasMore` and
  `isLoadingMore`, and returns early while loading (NET-005). Or model a
  page as a family (`productsPageProvider(page)`) so Riverpod de-duplicates
  and caches each page, as the Riverpod marvel example does.
- Cancellation: a use case or source accepts a `CancelToken?`; the notifier
  creates it and registers `ref.onDispose(token.cancel)` in `build()`.

## 3. MVVM (Flutter architecture guide)

```
lib/data/services/api/api_client.dart             one instance, created at the root
lib/data/services/api/model/booking_api_model.dart
lib/data/repositories/booking/booking_repository_remote.dart
lib/domain/models/booking/booking.dart
lib/ui/booking/view_models/booking_viewmodel.dart
```

- Services wrap the API; repositories own caching, mapping and error
  handling, and return `Result<T>`. View models depend on repositories and
  expose `Command`s.
- The compass sample creates a dart:io `HttpClient` per request through a
  factory and closes it in `finally`. That's a valid, testable style; an
  injected long-lived client is the alternative. Either way, set timeouts.
- Pagination: `late final loadMore = Command0(_loadMore);` A `Command`
  ignores `execute()` while it is running, which is exactly the in-flight
  guard NET-005 asks for.
- Cancellation: keep the token in the view model and cancel it in
  `dispose()`.

## 4. Bloc / Cubit

```
packages/catalog_api/lib/src/catalog_api_client.dart     data provider (its own package or folder)
packages/catalog_repository/lib/src/catalog_repository.dart
lib/catalog/bloc/catalog_bloc.dart
lib/app/bootstrap.dart                                     builds client + repository once
```

- The data provider takes an optional `http.Client` (or `Dio`) and exposes
  `close()`. The repository maps API models to domain models. The app
  provides the repository with `RepositoryProvider`; blocs get it by
  constructor.
- Pagination (bloclibrary's infinite list): register the fetch event with a
  transformer that drops events while one is running, and keep
  `hasReachedMax` in the state:

```dart
EventTransformer<E> throttleDroppable<E>(Duration d) =>
    (events, mapper) => droppable<E>().call(events.throttle(d), mapper);

on<PostFetched>(_onFetched, transformer: throttleDroppable(const Duration(milliseconds: 100)));
```

- Search-as-you-type: `restartable()` (with a debounce) cancels the stale
  handler, so an old response can't overwrite a new one (NET-stale-response).
- Cubit: `if (state.status == Status.loading || state.hasReachedMax) return;`
  then `emit(loading)` before the await.
- Cancellation and sockets: keep them in the bloc (or the repository
  subscription it listens to) and cancel/close in `close()`.

## 5. Clean Architecture (any state solution)

`data/datasources/remote/<x>_remote_data_source.dart` (contract + impl),
`data/models/<x>_model.dart` (DTO), `data/repositories/<x>_repository_impl.dart`
(maps models to `domain/entities`, exceptions to `Failure`, often
`Either<Failure, T>`). The domain layer never imports `dio`, `http` or a DTO
(ARCH-003). Whatever drives the UI (Bloc, Riverpod, Provider) follows its
section above.

## 6. Provider, GetX, plain Riverpod

- **Provider:** services are built in `MultiProvider` at the root with a
  `dispose:` that closes them; ChangeNotifiers call repositories and keep an
  `_isLoading` flag for "load more".
- **GetX:** one `GetConnect` or Dio registered permanently in the initial
  binding; repositories are `Get.lazyPut`; controllers keep `isLoading` as an
  `RxBool`, return early while it is true, and cancel tokens in `onClose()`.
- **Plain Riverpod:** a keepAlive client provider, repository providers that
  read it, and `FutureProvider.autoDispose(.family)` or notifiers for reads.
  Per-request `CancelToken` + `ref.onDispose(token.cancel)` in the provider
  that issues the request (the marvel and pub examples).

## 7. Lifetime hooks: cancel and close

| Pattern | Cancel a request / close a socket in |
|---|---|
| MVN / Riverpod | `ref.onDispose(token.cancel)` / `ref.onDispose(channel.sink.close)` in the provider or notifier `build()` |
| MVVM | the view model's `dispose()`; services closed by the root `Provider(dispose:)` |
| Bloc / Cubit | `close()` override, before `super.close()` |
| Provider (ChangeNotifier) | `dispose()` |
| GetX | `onClose()` |
| setState | `State.dispose()` (but the request belongs in a repository) |

A data-layer class that owns a socket gets its own `close()`, called by the
provider or root that created it (NET-007's note says where).
