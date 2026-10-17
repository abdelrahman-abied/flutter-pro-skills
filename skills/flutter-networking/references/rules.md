# NET rules: what the checker reports, and why

`scripts/check_networking.py` is static and read-only. It needs only the
Python standard library and no `pub get`. Every hit is a candidate: read the
code before you call a finding `confirmed`. Each rule lists the false
positives it knows about and how to suppress a deliberate case.

The checker judges what the architecture, security and error checkers can't
see: how the client is configured, who owns its lifetime, how retries and
"load more" behave, and how URLs are built. Where a concern already has an
owner in the suite, NET cross-references it instead of reporting it again
(section 4).

## Contents

1. How the checker reads the project
2. NET-001 … NET-010
3. Reading-level findings (NET-<slug>)
4. Not checked here (cross-references)
5. Calibration

## 1. How the checker reads the project

- **Scope.** Every `.dart` file under `lib/` that `arch_check` lists in
  `files[]`, minus barrels. Generated files are skipped: `*.g.dart`,
  `*.freezed.dart`, `*.chopper.dart`, files with a `GENERATED CODE - DO NOT
  MODIFY` banner, and OpenAPI Generator output (its "AUTO-GENERATED FILE"
  banner). A generated client is judged where your code wraps it.
- **Layers and roles** come from `../flutter-architecture/scripts/arch_check.py
  --json` (`files[]`). It reuses `$FPS_ARCH_JSON` when `dart-flutter-review`
  already ran it. Without the sibling skill, a path-based fallback is used and
  the `classification:` line says so.
- **Composition-root and `di` files are read**, because that is where the
  shared client is configured (NET-001). Rules about where a client is
  *created* (NET-002, NET-009) skip them.
- **Project-wide facts.** Base URL hosts are compared across files (NET-008),
  a global `Bloc.transformer = …` silences NET-005 for blocs, page-fetch
  methods are matched to their callers in every file, and top-level or static
  `const`/`final` names count as constants (NET-010).
- **Placement notes.** Each finding's `note` ends with the fix location for
  the detected profile (`MVN: …`, `MVVM: …`, `Bloc: …`, `Riverpod: …`,
  `Provider: …`, `GetX: …`, plus `Clean: …` when the project has domain and
  data layers). Lifetime rules (NET-005/006/007) carry the pattern's own
  mechanism instead: `ref.onDispose`, Bloc `close()`, `dispose()`,
  `onClose()`, a `Command`, a transformer. `--profile` overrides the detected
  pattern.
- **Suppression.** `// net-ignore: NET-00x <reason>` on the reported line or
  the line above it; `// net-ignore-file: NET-00x <reason>` anywhere in the
  file. The reason is kept in the JSON `suppressed` list.
- **ID note.** `flutter-security-audit`'s `scan.sh` uses uppercase word IDs
  such as `NET-ACCEPT-ALL` and `NET-CLEARTEXT`. This skill's script IDs are
  always numeric (`NET-0xx`) and its reading IDs are lowercase slugs
  (`NET-stale-response`). Keep scan.sh IDs verbatim when merging and dedupe by
  file and line.

## 2. Rules

### NET-001 client-without-timeouts

**Medium** when a Dio client has neither `connectTimeout` nor
`receiveTimeout` · **Low** when one of the two is missing, or for a dart:io
`HttpClient()` without `connectionTimeout` in a file with no `.timeout(` ·
all profiles

**Detects:** `Dio()` / `Dio(BaseOptions(...))` (also `Dio(options)` when
`options = BaseOptions(...)` is in the same file) without the timeouts, unless
the file sets `dio.options.connectTimeout = …` / `receiveTimeout = …` or
replaces `.options`.

**Why:** Dio's timeouts default to none, so a request on a captive portal, a
dead Wi-Fi or a stalled server never completes. The spinner never stops,
the error state never renders, and retry logic never runs. Timeouts belong on
the one shared client so every request inherits them.

```dart
// Bad
final dioProvider = Provider((ref) => Dio());

// Good
@Riverpod(keepAlive: true)
Dio apiClient(Ref ref) {
  final dio = Dio(BaseOptions(
    baseUrl: ref.watch(appConfigProvider).apiBaseUrl,
    connectTimeout: const Duration(seconds: 10),
    receiveTimeout: const Duration(seconds: 20),
  ));
  ref.onDispose(dio.close);
  return dio;
}
```

For package:http, which has no client-level timeout, wrap calls in
`.timeout(...)` inside your client wrapper (or give `IOClient` an
`HttpClient()..connectionTimeout = …`). The checker doesn't flag package:http
calls without `.timeout` (too common in canonical samples to grade fairly);
reviewers apply the same rule by reading.

**Known false positives:** options built by a helper in another file (not
reported: the checker can't see them); a `HttpClient()` inside a Dio
`IOHttpClientAdapter(createHttpClient: ...)` factory is not reported, because
Dio applies its own timeouts there.

### NET-002 client-created-per-call

**Medium** (**Low** inside an `Interceptor`, where a fresh client is a known
refresh trick) · data and other non-UI layers (views, widgets and logic are
ARCH-101/007/012's)

**Detects:** `Dio(` inside the body of a named method of a source, service,
repository or helper, when the client is not stored in a field, not returned
(a factory), and the method is not a provider function, a `build…/create…/
init…/configure…` factory or a constructor.

**Why:** each call gets a client without the shared auth interceptor,
timeouts, base URL and logging policy, opens its own connection pool, and
can't be replaced by a fake in tests.

```dart
// Bad
Future<List<ProductDto>> fetchProducts(int page) async {
  final dio = Dio();
  final res = await dio.get('https://api.shop.io/v1/products', queryParameters: {'page': page});
  ...
}

// Good: inject the configured client
class CatalogRemoteSource {
  CatalogRemoteSource(this._dio);
  final Dio _dio;
  Future<List<ProductDto>> fetchProducts(int page) async {
    final res = await _dio.get<List<dynamic>>('/products', queryParameters: {'page': page});
    ...
  }
}
```

When NET-002 fires on a line, NET-001 doesn't: the fix (inject the shared
client) removes both. **Known false positives:** a deliberately isolated
client (for example a refresh client that must skip the auth interceptor)
built per call; build it once instead, or suppress with a reason.

### NET-003 http-client-never-closed

**Low** · all profiles

**Detects:** a local `http.Client()`, `HttpClient()`, `IOClient(...)` or
`RetryClient(...)` in a function body that is never `close()`d, returned,
passed on, stored in a field or registered with `onDispose`; or
`http.Client().get(...)` inline.

**Why:** an unclosed client keeps its sockets alive until the idle timeout,
one set per call. A long-lived injected client is better; when a one-off
client is right (the Flutter compass sample creates one per request), close it
in `finally`.

```dart
// Bad
Future<String> search(String q) async {
  final client = http.Client();
  return (await client.get(uri)).body;
}

// Good
Future<String> search(String q) async {
  final client = http.Client();
  try {
    return (await client.get(uri)).body;
  } finally {
    client.close();
  }
}
```

### NET-004 retry-resends-any-method

**Medium** · all profiles

**Detects:** a Dio `Interceptor` / `QueuedInterceptor` subclass or an
`InterceptorsWrapper(onError: ...)` whose `onError` re-sends the request
(`dio.fetch(err.requestOptions)`, `.request(...)`, directly or through a
helper of the same class) with no check of `requestOptions.method`, no
idempotency key and no 401/403 gate.

**Why:** a timeout doesn't mean the server didn't act. Retrying a POST that
reached the server creates a second order, message or payment. Retry only
idempotent methods, only on transient failures, with backoff; for writes,
send a client-generated `Idempotency-Key` the backend honours.

```dart
// Bad
@override
Future<void> onError(DioException err, ErrorInterceptorHandler handler) async {
  if (err.type == DioExceptionType.connectionTimeout) {
    return handler.resolve(await _dio.fetch(err.requestOptions));
  }
  handler.next(err);
}

// Good
static const _idempotent = {'GET', 'HEAD', 'PUT', 'DELETE', 'OPTIONS'};

@override
Future<void> onError(DioException err, ErrorInterceptorHandler handler) async {
  final opts = err.requestOptions;
  final attempt = (opts.extra['attempt'] as int?) ?? 0;
  if (_isTransient(err) && attempt < 3 &&
      (_idempotent.contains(opts.method) || opts.headers.containsKey('Idempotency-Key'))) {
    await Future<void>.delayed(_backoff(attempt));          // 0.5 s, 1 s, 2 s + jitter
    opts.extra['attempt'] = attempt + 1;
    return handler.resolve(await _dio.fetch(opts));
  }
  handler.next(err);
}
```

**Not reported:** a 401-gated replay after a token refresh (the server
rejected the request, so replaying it is safe; refresh is
`flutter-secure-defaults`' concern). Package retry helpers (`dio_smart_retry`'s
`RetryInterceptor`, package:http's `RetryClient`) are not judged by the
script: check their method and status filters when you read the code. Offline
replay of queued writes is the repository's job
(`flutter-persistence`, PERSIST-non-idempotent-retry).

### NET-005 page-fetch-without-guard

**Medium** when a scroll callback calls it without a check · **Low** when it
is triggered another way (a button) or no caller was found · bloc, cubit and
every logic holder

**Detects:**
- **Bloc:** `on<E>(handler)` with no `transformer:` where `E` or the handler
  looks like pagination (`…More`, `…NextPage…`, `…PageRequested`,
  `…Scrolled`, or a body using `hasReachedMax`, `nextPage`, `nextCursor`,
  `startIndex:`), the handler awaits, and it has no
  `if (… loading …) return` before the await. A project-wide
  `Bloc.transformer = …` silences it.
- **Cubit, notifier, view model, controller:** a method named `loadMore…`,
  `fetchMore…`, `loadNext`/`getNext`/`fetchNext[Page]`, `…NextPage…`,
  `onEndReached`, `onLoadMore`, `paginate` that awaits with no in-flight check
  before the first await. When the method *sets* a loading flag before the
  await, the guard may live in the callers: it is reported only when a caller
  calls it without checking an in-flight flag.

**Why:** scroll listeners and `itemBuilder` thresholds fire many times per
second near the end of a list. Without a guard the same page is requested
several times and appended twice. Bloc processes events concurrently by
default, so `hasReachedMax` alone doesn't stop it: bloclibrary's infinite-list
tutorial registers the fetch with a `throttleDroppable` transformer for this
reason.

```dart
// Bloc: drop events while one is running (bloc_concurrency)
on<PostFetched>(_onFetched, transformer: droppable());

// Notifier (MVN / Riverpod)
Future<void> loadMore() async {
  if (state.isLoadingMore || !state.hasMore) return;
  state = state.copyWith(isLoadingMore: true);
  ...
}

// MVVM: a Command ignores execute() while running
late final loadMore = Command0(_loadMore);
```

**Known false positives:** a guard in a base class or mixin; a caller-side
guard the checker can't connect to the method (calls are matched by method
name and the receiver's provider or class name). Suppress with a reason.

### NET-006 cancel-token-never-cancelled

**Low** · all profiles

**Detects:** `CancelToken()` assigned to a name on which `.cancel` is never
used in the file (not counting tokens returned to a caller), or created
inline (`cancelToken: CancelToken()`). A `cancelToken ?? CancelToken()`
default is not reported: the caller supplied the cancellable one.

**Why:** a token nobody cancels cancels nothing, while the code reads as if
requests stop when the user leaves. Tie it to the lifetime of whoever started
the request.

```dart
// Riverpod (riverpod.dev "cancel" recipe)
final itemDetail = FutureProvider.autoDispose.family<Item, String>((ref, id) async {
  final token = CancelToken();
  ref.onDispose(token.cancel);
  return ref.watch(itemRepositoryProvider).detail(id, cancelToken: token);
});

// Bloc: keep it in the bloc, cancel in close()
@override
Future<void> close() {
  _token.cancel();
  return super.close();
}
```

In a data-layer class, prefer taking the token as a parameter from the logic
holder that owns the request's lifetime.

### NET-007 websocket-never-closed

**Medium** · all profiles (placement in UI or logic is ARCH-005/007's)

**Detects:** `WebSocketChannel.connect(`, `IOWebSocketChannel.connect(`,
`HtmlWebSocketChannel.connect(` or dart:io `WebSocket.connect(` whose result
is stored (or used inline) and never closed in the file (`.sink.close(`,
`.close(`, or a reference in `onDispose(`), unless it is returned or handed
to another owner.

**Why:** the socket, its server session and its stream outlive the screen or
provider that opened it; every reopen adds a connection, and the server keeps
pushing to a listener nobody reads.

```dart
class PricesSource {
  WebSocketChannel? _channel;

  Stream<dynamic> connect(Uri uri) {
    _channel = WebSocketChannel.connect(uri);
    return _channel!.stream;
  }

  Future<void> close() async => _channel?.sink.close(status.normalClosure);
}
// MVN / Riverpod: ref.onDispose(source.close) in the source's provider
```

### NET-008 base-url-duplicated

**Low** · all profiles · automates the documented
`AP-hardcoded-config-in-sources` (flutter-architecture) for API hosts

**Detects:** the same `scheme://host` (or `Uri.https('host', ...)`) used in an
API context (`BaseOptions`/`Dio(`, `baseUrl:`, a client call, or a constant
named `_base…`, `…Api…`, `…Host…`, `…Endpoint…`, `…Server…`) in two or more
files. One finding per extra file; when one of the files is a config,
constants, env or endpoints file, the others are reported and pointed at it.

**Why:** switching environments or flavors needs edits in many places, and one
is always missed: a staging build that writes to production.

**Not reported:** browser links (`launchUrl`, `canLaunchUrl`, `Link`), image
URLs (`Image.network`, `NetworkImage`, names with image/icon/avatar/photo),
local and example hosts, and public code or content hosts (GitHub, raw
GitHub content, CDNs, store pages): those aren't your API base.

### NET-009 top-level-http-call

**Low** · data and other non-UI layers (widgets are ARCH-101's)

**Detects:** `http.get/post/put/patch/delete/head/read/readBytes(` through the
package:http import prefix in a class or function outside the UI, logic,
domain and composition root. The note says when the class already holds an
injected `http.Client` it should have used.

**Why:** each top-level call builds and closes a throwaway client: no
connection reuse, no shared headers, no timeout policy, and tests can't swap
in `MockClient`.

```dart
// Bad
Future<String> banner() async => (await http.get(Uri.https(host, '/banner.json'))).body;

// Good
class BannerSource {
  BannerSource(this._client);
  final http.Client _client;
  Future<String> banner() async => (await _client.get(Uri.https(host, '/banner.json'))).body;
}
```

### NET-010 query-value-not-encoded

**Low** · all profiles

**Detects:** a string interpolation right after `?name=` or `&name=` in an
HTTP URL (a literal starting with `http(s)://`, or built from a
`base`/`url`/`host` value, or passed to `Uri.parse` or a client call), when
the value is a `String` parameter or local, `controller.text`, or a text-like
name (`query`, `term`, `search`, `filter`, `name`, `email` …). Numbers,
id-like names (`id`, `…Id`, `page`, `limit`), constants and values wrapped in
`Uri.encodeQueryComponent` are not reported.

**Why:** `&`, `#`, `+` and spaces change or truncate the query ("c#" searches
for "c"), and a crafted value can add parameters.

```dart
// Bad
_client.get(Uri.parse('$baseUrl/search?q=$query'));

// Good
_client.get(Uri.parse(baseUrl).replace(path: '/search', queryParameters: {'q': query}));
_dio.get('/search', queryParameters: {'q': query});
```

App route locations (`'/gallery?item=$itemId'`) are not HTTP requests and are
left to `flutter-navigation`.

## 3. Reading-level findings (NET-<slug>)

The checker can't see these reliably. Look for them when you review API code.

| ID | Severity | Look for | Fix |
|---|---|---|---|
| NET-unvalidated-json | Medium | `fromJson` that hard-casts server fields (`json['user'] as Map<String, dynamic>`) with no check, so one odd payload throws a `TypeError` that no `on DioException` catches | validate at the DTO boundary: `json_serializable` with `checked: true`, or a `switch (json) { case {'id': String id} => … }` that throws `FormatException`, mapped to a failure in the repository (`dtos-and-json.md`) |
| NET-stale-response | Medium | search-as-you-type or filter changes where an older response can land after a newer one | Bloc `restartable()`, cancel the previous `CancelToken`, a Riverpod family keyed by the query, or compare a request id before applying |
| NET-retry-without-backoff | Medium | a retry loop or interceptor with no delay, no cap or no jitter, or retrying 4xx and parse failures | exponential backoff with jitter and a cap, transient failures only (`requests.md` §3); idempotency is NET-004 |
| NET-websocket-reconnect-storm | Medium | a socket that reconnects immediately on every close, with no backoff and no stop when the owner is gone | backoff with jitter, reset on success, stop on dispose (`requests.md` §6) |
| NET-upload-in-memory | Medium | `readAsBytes()` of a large file for `MultipartFile.fromBytes`, or a download buffered in memory | `MultipartFile.fromFile`, `dio.download(url, path)`, or a streamed request; report progress with `onSendProgress`/`onReceiveProgress` |
| NET-no-cancellation | Low | requests started by an auto-disposed provider, a screen or a bloc with no way to cancel them, applying results after the owner is gone | a `CancelToken` tied to the owner's lifetime (NET-006 shows the per-pattern hook) |
| NET-interceptor-order | Low | logging added before auth or retry, so the log shows a request that is not what was sent (or misses retries) | add auth, then retry, then logging (`client-setup.md` §3) |
| NET-no-fake-seam | Low | a client reached through a static singleton or top-level `final`, so tests can't inject a fake | constructor or provider injection (`testing-with-fakes.md`) |

## 4. Not checked here (cross-references)

| Concern | Owner | Why NET stays out |
|---|---|---|
| auth headers built outside the data layer | SEC-002 (`flutter-secure-defaults`) | refresh, single-flight and logout also live there |
| cleartext `http://` / `ws://` | SEC-003 | |
| HTTP loggers in release builds; bodies logged | SEC-005 / SEC-011 | NET-interceptor-order is only about order |
| accept-any-certificate; pinning | SEC-006; `flutter-security-audit` | |
| tokens in storage or URLs | SEC-001; NAV-006 for PII in URLs | |
| `Dio(`/`http.get(` in widgets; transport imports in views, logic or domain | ARCH-101 / ARCH-005 / ARCH-007 / ARCH-012 / ARCH-003 | NET-002 and NET-009 skip those layers |
| repositories returning `Response`, `Map` or DTOs | ARCH-107 (and ARCH-006) | |
| `DioException`/`SocketException` escaping repositories | ERR-004 | mapping is in `flutter-error-handling` |
| unguarded I/O in UI callbacks | ERR-014 | |
| automatic retry of non-idempotent calls outside an interceptor | ERR-retry-non-idempotent (reading) | NET-004 beats it on the same line |
| large JSON decoded on the UI isolate | PERF-011 (`flutter-performance`) | |
| cache policy, offline queues, connectivity treated as truth | PERSIST-no-cache-policy, PERSIST-non-idempotent-retry, PERSIST-connectivity-as-truth | the client's retry policy is NET's, offline replay is PERSIST's |
| untrusted URL launches | NAV-005 | |
| real network in tests | TEST smells (`flutter-testing`) | |

## 5. Calibration

Run on the suite's shared calibration pool (§24 and §27 of the suite
contracts). Each project with its own `pubspec.yaml` and `lib/` was run
separately. Every high and medium hit was read and judged by the pattern's
canonical source; low hits were read too.

| App | Commit | Profile | Networking seen | Hits (per rule) | TP / FP |
|---|---|---|---|---|---|
| flutter/samples `compass_app` (canonical) | flutter/samples@5541c59 | mvvm | dart:io `HttpClient` through a factory, closed per call | none | 0 / 0 |
| felangel/bloc `examples/*` + `packages/*`, 40 projects (canonical) | felangel/bloc@b9be1e2 | bloc | `http.Client` injected; infinite list with `throttleDroppable` | none | 0 / 0 |
| rrousselGit/riverpod `examples/*`, 7 projects (canonical) | rrousselGit/riverpod@1efba1c | riverpod | Dio (marvel, pub, stackoverflow, first_app), `ref.onDispose(cancelToken.cancel)` | NET-001 ×4 (medium) | 4 / 0 |
| lichess-org/mobile | lichess-org/mobile@99e1fb7 | riverpod | package:http + `RetryClient`, WebSockets, 4 page handlers | NET-005 ×1 (low) | 1 / 0 |
| immich-app/immich `mobile` (+ `mobile/packages/*`) | immich-app/immich@188d64e | riverpod + clean | generated OpenAPI client, package:http, socket.io | none | 0 / 0 |
| hiddify/hiddify-app | hiddify/hiddify-app@83911ed | riverpod | Dio with `dio_smart_retry`, proxy adapters, CancelTokens | NET-006 ×1 (low) | 1 / 0 |
| gskinnerTeam/flutter-wonderous-app (extra) | gskinnerTeam/flutter-wonderous-app@747b945 | provider | package:http | NET-008 ×1, NET-009 ×2 (low) | 3 / 0 |
| flutter/samples, the other projects (extra) | flutter/samples@5541c59 | various | package:http | NET-009 ×5 (low: desktop_photo_search ×2 twice, google_maps) | 5 / 0 |
| simolus3/drift `examples/app` (extra) | simolus3/drift@c907be8 | riverpod | none | none | 0 / 0 |

**The canonical medium hits are true positives.** The four Riverpod examples
build `Dio()` with no options. Dio's connect and receive timeouts default to
none, so on a dead network those requests hang forever; the fix is two
`BaseOptions` fields on the one shared client. The Riverpod docs don't
prescribe timeouts either way; Dio's own documentation sets them.

**Other true positives.** lichess's message "load older" button awaits with
no guard, so a double tap fetches and prepends the same page twice (Low,
button-triggered). hiddify passes an inline `CancelToken()` nobody can cancel.
wonderous repeats its museum API base in a dev tool and in the service, and
calls `http.get`/`http.readBytes` top-level. desktop_photo_search's API class
holds an injected `http.Client` but calls `http.get`/`http.readBytes` in two
methods, bypassing it.

**False-positive causes fixed.** Each cause has a `calib_*` regression
fixture (fresh minimal code, no lines or names from the apps) plus a test
that the related true positive still fires.

| Cause | Seen in | Hits before | Fix | Fixture |
|---|---|---|---|---|
| a notifier sets `isLoading: true` before the await and every scroll caller checks `!isLoading` first | lichess (×3) | NET-005 medium | a flag set before the await counts as a guard when every caller checks it; callers are matched by method name and receiver | `calib_lichess` |
| "next single item" and explicit page jumps (a "load next round" step, a jump to an explicit page number) taken for infinite-scroll fetches | lichess (×3) | NET-005 medium | the method vocabulary is limited to more/next-page names | `calib_lichess` |
| a button inside `itemBuilder` treated as a scroll trigger | lichess | NET-005 medium (now Low, a TP) | `onPressed`/`onTap` closures are button triggers (Low) | `calib_lichess` |
| `launchUrl(Uri.parse('https://own-site/...'))` links in many widgets | lichess (×8), immich | NET-008 low | browser-link and image calls are not API contexts | `calib_lichess` |
| `imageUrl:` sample data in a data service and a widget | compass_app | NET-008 low | a plain `url` name is not an API context; image names are excluded | `calib_compass` |
| different repositories on a public content host (`raw.githubusercontent.com`) | hiddify (×4) | NET-008 low | public code/content hosts are excluded | `calib_hiddify` |
| an image base path named `base…` | wonderous | NET-008 low | names with image/photo/icon/avatar are excluded | `calib_wonderous` |
| dart:io `HttpClient()` inside Dio's `IOHttpClientAdapter(createHttpClient: ...)` | hiddify | NET-001 low | adapter factories are skipped (Dio's timeouts apply) | `calib_hiddify` |
| `cancelToken ?? CancelToken()` default for a caller-supplied token | hiddify | NET-006 low | `??` defaults are not reported | `calib_hiddify` |
| an app route location with an id in its query | wonderous | NET-010 low | only HTTP request URLs; id-like names are URL-safe | `calib_wonderous` |
| `?utm_source=$appName` with a top-level `const` | desktop_photo_search (×2 per variant) | NET-010 low | project-wide `const`/`final` names are constants | `calib_samples` |

**False negative fixed:** `_baseUrl`-style names (a leading underscore) were
not recognised as API base constants. Covered by `calib_wonderous`.
