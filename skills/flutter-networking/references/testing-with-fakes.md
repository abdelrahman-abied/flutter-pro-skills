# Testing the API layer with fake clients

Tests never touch the real network. The injected client is the seam: swap it
for a fake at the lowest level that keeps the test meaningful. Which layer to
test first per architecture, and fakes versus mocks, are
`flutter-testing`'s (load that skill; fallback `../flutter-testing/SKILL.md`).

## Contents

1. What to test where
2. package:http: MockClient
3. Dio: a fake HttpClientAdapter
4. Dio: http_mock_adapter
5. Above the source: fake repositories
6. What to assert

## 1. What to test where

| Layer | Fake | Proves |
|---|---|---|
| remote source | a fake HTTP client (below) | paths, query parameters, headers, body encoding, status handling, DTO parsing |
| repository | a fake source (or the source over a fake client) | DTO → entity mapping, error → failure mapping, pagination cursors |
| interceptors | a fake adapter that fails then succeeds | retry only idempotent methods, backoff count, 401 → refresh → replay |
| logic (notifier, view model, bloc) | a fake repository | loading/error/data states, the in-flight guard, cancellation on dispose |

## 2. package:http: MockClient

```dart
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

test('search encodes the query and parses results', () async {
  late Uri seen;
  final client = MockClient((request) async {
    seen = request.url;
    return http.Response(jsonEncode([{'id': '1', 'title': 'c#'}]), 200,
        headers: {'content-type': 'application/json'});
  });
  final source = CatalogRemoteSource(client, baseUrl: Uri.parse('https://api.test'));

  final items = await source.search('c#');

  expect(seen.queryParameters['q'], 'c#');
  expect(items.single.title, 'c#');
});
```

This is why NET-009 asks for an injected `http.Client`: top-level `http.get`
can't be replaced.

## 3. Dio: a fake HttpClientAdapter

No extra package; the adapter sees exactly what Dio would send.

```dart
class FakeAdapter implements HttpClientAdapter {
  FakeAdapter(this.handler);
  final Future<ResponseBody> Function(RequestOptions options) handler;
  final requests = <RequestOptions>[];

  @override
  Future<ResponseBody> fetch(RequestOptions options, Stream<Uint8List>? requestStream, Future<void>? cancelFuture) {
    requests.add(options);
    return handler(options);
  }

  @override
  void close({bool force = false}) {}
}

ResponseBody json(Object body, [int status = 200]) => ResponseBody.fromString(jsonEncode(body), status,
    headers: {Headers.contentTypeHeader: [Headers.jsonContentType]});

test('retries a timed-out GET once, never a POST', () async {
  var calls = 0;
  final dio = buildApiClient(config)..httpClientAdapter = FakeAdapter((o) async {
    calls++;
    if (calls == 1) {
      throw DioException.connectionTimeout(timeout: const Duration(seconds: 1), requestOptions: o);
    }
    return json({'ok': true});
  });

  await dio.get<void>('/items');
  expect(calls, 2);
});
```

Build the client with the *production* builder and replace only the adapter,
so the test covers your interceptors and options too.

## 4. Dio: http_mock_adapter

```dart
final dio = Dio(BaseOptions(baseUrl: 'https://api.test'));
final adapter = DioAdapter(dio: dio);
adapter.onGet('/products', (server) => server.reply(200, [{'id': '1', 'title': 'A'}]),
    queryParameters: {'page': 1});
```

Handy for many endpoints; the hand-written adapter above is enough for a few.

## 5. Above the source: fake repositories

Logic tests fake the repository contract, not the client:

```dart
class FakeCatalogRepository implements CatalogRepository {
  final pages = <int, List<Product>>{};
  var calls = 0;
  @override
  Future<List<Product>> page(int page) async {
    calls++;
    return pages[page] ?? const [];
  }
}
```

- **MVN / Riverpod:** `ProviderContainer(overrides: [catalogRepositoryProvider.overrideWithValue(fake)])`.
- **Bloc:** `blocTest` with the fake injected; to prove the transformer,
  `act: (b) => b..add(NextPageRequested())..add(NextPageRequested())` and
  `verify: (_) => expect(fake.calls, 1)`.
- **MVVM:** construct the view model with the fake; call
  `loadMore.execute()` twice without awaiting; expect one repository call.

## 6. What to assert

- Requests: method, path, query parameters (decoded), headers you own (not
  the auth token's value), body.
- Mapping: every DTO field reaches the entity; unknown enum values fall back.
- Failures: a 500, a timeout, a malformed body and a cancellation each map to
  the expected failure (or to "no result" for cancellation).
- Lifetime: disposing the container, closing the bloc or disposing the view
  model cancels the token or closes the socket.

Don't assert on log output, and don't use real hosts, `sleep`, or a running
local server for unit tests (TEST smells).
