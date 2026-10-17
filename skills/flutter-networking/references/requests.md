# Requests: pagination, cancellation, retry, transfers, WebSockets

## Contents

1. Pagination
2. Cancellation
3. Retry with backoff
4. Connectivity
5. Uploads and downloads with progress
6. WebSockets

## 1. Pagination

The repository fetches **one page** (`Future<Page<Product>> page({String?
cursor, int limit})`); the logic holder keeps the list, the cursor or page,
`hasMore`, and an in-flight flag.

- **Cursor or page?** Prefer the server's cursor (`next`, `nextCursor`,
  `until: last.createdAt`) when it has one: inserts and deletes don't shift
  it. Page or offset is fine for static lists.
- **The in-flight guard** is what NET-005 checks. Scroll listeners and
  `itemBuilder` thresholds fire repeatedly near the end of a list; without a
  guard you request the same page twice and append duplicates.

| Pattern | Guard |
|---|---|
| Bloc | `on<NextPageRequested>(_onNext, transformer: droppable())` (bloc_concurrency); bloclibrary's infinite list throttles too |
| Cubit | `if (state.status == Status.loadingMore || state.hasReachedMax) return;` then `emit(loadingMore)` before the await |
| MVN / Riverpod notifier | `if (state.isLoadingMore || !state.hasMore) return;` and set the flag before the await; or a page family provider |
| MVVM | expose `loadMore` as a `Command0`; `execute()` ignores calls while `running` |
| Provider / GetX | a private `_isLoading` / `RxBool` checked first and reset in `finally` |

- **Refresh vs load more:** a refresh replaces the list and resets the cursor;
  make an in-flight load-more's result ignorable (compare a generation
  counter) so it can't append to the new list.
- **Search and filters:** cancel or ignore the previous request when the
  query changes (Bloc `restartable()`, a family keyed by the query, cancel the
  previous `CancelToken`), or an old response lands after the new one
  (NET-stale-response).
- **Packages:** `infinite_scroll_pagination`'s `PagingController` already
  serializes page requests; keep its listener thin and call the repository.

## 2. Cancellation

Cancel when the owner of the request goes away (the user left the screen, the
query changed), not as error handling.

- **Dio:** `CancelToken`; `token.cancel()` makes the pending request fail with
  `DioExceptionType.cancel`. Treat that as "no result", never as an error to
  show.
- **package:http:** close a dedicated client, or use an abortable request
  (recent package:http versions accept an abort trigger on the request).
- **Hooks per pattern** (`placement-by-architecture.md` §7):

```dart
// Riverpod / MVN (the marvel and pub examples)
final token = CancelToken();
ref.onDispose(token.cancel);

// Bloc
@override
Future<void> close() {
  _token?.cancel();
  return super.close();
}

// MVVM / ChangeNotifier
@override
void dispose() {
  _token?.cancel();
  super.dispose();
}
```

A token nobody cancels is NET-006. Pass tokens down from the logic holder to
the source; a source that creates its own tokens can't know when to cancel.

## 3. Retry with backoff

The retry *policy in the HTTP client* belongs here; replaying queued writes
after being offline is the repository's (`flutter-persistence`,
`../flutter-persistence/references/caching-and-offline.md`), and showing a retry button is
`flutter-error-handling`'s.

- **What:** transient failures only: connection errors, timeouts, 502/503/504,
  and 429 honouring `Retry-After`. Never 4xx (other than 408/429), never parse
  failures, never cancellations.
- **Which requests:** idempotent methods (GET, HEAD, PUT, DELETE, OPTIONS).
  POST and PATCH only with an `Idempotency-Key` the server honours (NET-004).
- **How:** exponential backoff with jitter and a cap: for example
  `min(cap, base * 2^attempt) * random(0.5, 1.0)`, three attempts, base 500 ms.
  Store the attempt count in `requestOptions.extra`.
- **Where:** one retry interceptor on the shared client (after auth, before
  logging; `client-setup.md` §3). Packages: `dio_smart_retry` (check which
  methods and statuses it retries), package:http's `RetryClient` (its default
  retries any method on 503: pass `when:` and `whenError:`).
- Riverpod already retries failing providers with backoff on recent
  versions; don't stack a client retry and a provider retry on the same call
  without meaning to.

## 4. Connectivity

`connectivity_plus` tells you which interface is up, not whether the server is
reachable. Use it as a hint (show an offline banner, pause a sync), never as a
gate before a request: try the request and treat the failure as offline.
`flutter-persistence` owns this rule (PERSIST-connectivity-as-truth).

## 5. Uploads and downloads with progress

```dart
// Upload from disk, streamed (not readAsBytes)
final form = FormData.fromMap({'file': await MultipartFile.fromFile(path, filename: name)});
await _dio.post<void>('/uploads', data: form, cancelToken: token,
    onSendProgress: (sent, total) => onProgress(total > 0 ? sent / total : null));

// Download straight to a file
await _dio.download(url, savePath, cancelToken: token,
    onReceiveProgress: (received, total) => onProgress(total > 0 ? received / total : null));
```

- Report progress as a stream or callback from the repository, mapped to a
  domain value (`UploadProgress`), and hold it in the logic holder's state.
- package:http: `http.MultipartRequest` with `MultipartFile.fromPath`, sent with
  `client.send`; for progress, count bytes of a `StreamedRequest` or of the
  `StreamedResponse.stream` against `contentLength`.
- Big or background transfers that must survive the app being killed belong to
  a background-transfer plugin or the platform's download manager.
- Buffering a large file in memory is NET-upload-in-memory.

## 6. WebSockets

```dart
class TickerSource {
  WebSocketChannel? _channel;

  Stream<Tick> connect(Uri uri) async* {
    final channel = WebSocketChannel.connect(uri);   // wss:// only (SEC-003)
    _channel = channel;
    await channel.ready.timeout(const Duration(seconds: 10));
    yield* channel.stream.map((e) => TickDto.fromJson(jsonDecode(e as String)).toEntity());
  }

  Future<void> close() async => _channel?.sink.close(status.normalClosure);
}
```

- **Close on dispose** (NET-007): the provider or root that creates the source
  calls `close()`; a bloc listening to it cancels its subscription in
  `close()`.
- **Reconnect with backoff and jitter**, reset after a stable connection, and
  stop when the owner is disposed (NET-websocket-reconnect-storm). Resubscribe
  to topics after reconnecting; resend unacknowledged messages only if the
  protocol makes them idempotent.
- **Heartbeats:** a ping or app-level keepalive detects half-open sockets that
  never report closure.
- **Auth:** a short-lived ticket, not the long-lived refresh token
  (`flutter-secure-defaults`, `network-and-auth.md` §7).
- Expose a domain stream from the repository; logic subscribes the way its
  pattern prescribes (`emit.forEach` in Bloc, `StreamProvider`/notifier in
  Riverpod).
