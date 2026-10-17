# Client setup: one configured client, injected

Every networking default in this skill follows from one decision: the app has
**one configured client per backend**, built in the composition root and
injected into remote sources. Base URL, timeouts, interceptors, adapters and
logging policy live there, so no request can skip them and tests replace a
single seam.

## Contents

1. Choosing the client
2. The shared client, per DI style
3. Interceptors and their order
4. Timeouts
5. Environments and base URLs
6. Generated clients (retrofit, chopper, OpenAPI)

## 1. Choosing the client

| Client | Pick it when | Notes |
|---|---|---|
| `package:http` | small apps, packages, the Flutter cookbook and the bloc examples | `http.Client` is the seam; no interceptors, so wrap it (`BaseClient`) for headers, timeouts and retries; `MockClient` for tests |
| Dio | interceptors, cancellation, progress, `FormData`, per-request options | `BaseOptions` for defaults; `CancelToken`; `HttpClientAdapter` for tests and platform stacks |
| retrofit (on Dio) | many endpoints you'd otherwise hand-write | annotations generate the source class; it still takes your configured Dio |
| chopper (on http) | the same, on package:http | interceptors and converters; give it a configured `http.Client` |
| OpenAPI-generated client | the backend publishes an OpenAPI spec | treat it as a generated data source; wrap it, never let its models leave the data layer |
| `GetConnect` | GetX apps | configure `httpClient.baseUrl`, `httpClient.timeout`, request modifiers in `onInit` |
| platform stacks (`cupertino_http`, `cronet_http`, `ok_http`) | system proxy, VPN, HTTP/3 or certificate handling of the OS | plug in as the `http.Client` (or a Dio adapter) at the composition root; nothing else changes |

Keep one choice per backend. Two clients for one API means two policies.

## 2. The shared client, per DI style

**Riverpod / MVN (codegen).** A keepAlive provider owns the client and closes
it on dispose. Remote sources read it; nothing in presentation does.

```dart
@Riverpod(keepAlive: true)
Dio apiClient(Ref ref) {
  final config = ref.watch(appConfigProvider);
  final dio = Dio(BaseOptions(
    baseUrl: config.apiBaseUrl,
    connectTimeout: const Duration(seconds: 10),
    receiveTimeout: const Duration(seconds: 20),
    sendTimeout: const Duration(seconds: 20),      // uploads; not applied to GET
  ));
  dio.interceptors.addAll([
    AuthInterceptor(ref.watch(tokenStoreProvider)),  // flutter-secure-defaults
    RetryInterceptor(dio),                           // requests.md §3
    if (kDebugMode) LogInterceptor(requestHeader: false, requestBody: false, responseBody: false),
  ]);
  ref.onDispose(dio.close);
  return dio;
}

@Riverpod(keepAlive: true)
CatalogRemoteSource catalogRemoteSource(Ref ref) => CatalogRemoteSource(ref.watch(apiClientProvider));
```

**get_it / injectable.** Register the client as a lazy singleton once; register
sources with it.

```dart
getIt
  ..registerLazySingleton<Dio>(() => buildApiClient(getIt<AppConfig>()), dispose: (d) => d.close())
  ..registerLazySingleton<CatalogRemoteSource>(() => CatalogRemoteSource(getIt<Dio>()));
```

**Provider (and the Flutter MVVM guide).** Build services at the root and pass
them down by constructor. The compass sample builds `ApiClient` once in its
dependency list and hands it to the repositories.

```dart
MultiProvider(providers: [
  Provider(create: (_) => ApiClient(host: config.host), dispose: (_, c) => c.close()),
  Provider(create: (context) => BookingRepositoryRemote(apiClient: context.read())),
], child: const App());
```

**Bloc.** bloclibrary keeps the API client in its own data-provider package
(`open_meteo_api`, `github_client`), created once in `main`/`bootstrap`, passed
to the repository, and exposed with `RepositoryProvider`. Blocs receive the
repository. The client takes an optional `http.Client` so tests inject a mock:

```dart
class WeatherApiClient {
  WeatherApiClient({http.Client? httpClient}) : _httpClient = httpClient ?? http.Client();
  final http.Client _httpClient;
  void close() => _httpClient.close();
}
```

**GetX.** One `GetConnect` (or Dio) registered permanently in the initial
binding; controllers call repositories.

```dart
class ApiClient extends GetConnect {
  @override
  void onInit() {
    httpClient.baseUrl = Env.apiBaseUrl;
    httpClient.timeout = const Duration(seconds: 15);
    super.onInit();
  }
}
Get.put(ApiClient(), permanent: true);
```

What the shared client replaces: `Dio()` inside a method (NET-002), top-level
`http.get` in a source (NET-009), and clients nobody closes (NET-003).

## 3. Interceptors and their order

Dio runs request interceptors in the order they were added. Add them as
**auth → retry → logging**:

1. **Auth** attaches the access token and handles a 401 by refreshing once
   (single-flight) and replaying. Everything about tokens and refresh is in
   `flutter-secure-defaults` (`../flutter-secure-defaults/references/network-and-auth.md`); don't
   restate it here.
2. **Retry** re-sends transient failures of idempotent requests with backoff
   (`requests.md` §3). Because a retry goes back through `dio.fetch`, the
   replay picks up the current token.
3. **Logging** last, so it records what was really sent, including retries.
   Debug-only and without headers or bodies (SEC-005, SEC-011).

Other interceptors (headers such as `Accept-Language`, request ids, metrics)
go before retry. Keep each interceptor single-purpose; one that does auth,
retry and logging is untestable.

For package:http, the same layering is a chain of `BaseClient` wrappers:

```dart
http.Client buildHttpClient(TokenStore tokens) =>
    LoggingClient(RetryingClient(AuthClient(IOClient(HttpClient()..connectionTimeout = _connect), tokens)));
```

## 4. Timeouts

- **Dio:** set `connectTimeout` and `receiveTimeout` on `BaseOptions`
  (NET-001); add `sendTimeout` for uploads. Per-request overrides go in
  `Options(receiveTimeout: …)` for a known-slow endpoint, never a global
  "no timeout".
- **package:http:** there is no client-level timeout. Use
  `HttpClient()..connectionTimeout` under `IOClient`, and `.timeout(...)` on
  the request future inside your client wrapper, so call sites never repeat
  it.
- **WebSockets:** `WebSocket.connect(...).timeout(...)` or
  `await channel.ready.timeout(...)` for the handshake.
- **Pick values from your API**, not from habit: 10 s connect and 20–30 s
  receive are common starting points. A timeout surfaces as
  `DioExceptionType.connectionTimeout`/`receiveTimeout` or
  `TimeoutException`; map it in the repository (`flutter-error-handling`).

## 5. Environments and base URLs

Keep the base URL in one configuration value per flavor (an `AppConfig`
provided at the root, built from `--dart-define-from-file` or flavor
entry points) and give it to the one client. Sources use relative paths
(`'/products'`). The same host repeated across files is NET-008; secrets
never go in that config (`flutter-secure-defaults`, SEC-008/009).

## 6. Generated clients (retrofit, chopper, OpenAPI)

- **retrofit:** the generated `_CatalogApi` takes your configured `Dio`
  (`CatalogApi(dio)`), so timeouts and interceptors apply. Use
  `@CancelRequest()` for a `CancelToken` and `@SendProgress()` /
  `@ReceiveProgress()` for progress. The annotated interface *is* the remote
  source; the repository maps its DTOs.
- **chopper:** construct one `ChopperClient(baseUrl:, services:, converter:,
  interceptors:, client: configuredHttpClient)` at the root.
- **OpenAPI Generator:** the generated `ApiClient`/`*Api` classes are data
  sources. Configure the transport they use (the dart-dio generator takes a
  `Dio`; the dart generator takes an `http.Client`) at the root, wrap the
  generated APIs in your remote source or repository, and map generated
  models to entities there. The checker skips generated files; review the
  wrapper.

For step-by-step package setup, follow the package docs and, if your agent
has them installed, the official `flutter/agent-plugins` or `dart-lang/skills`
recipes and the docs.flutter.dev networking cookbook.
