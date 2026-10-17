# Isolates: moving work off the UI isolate, in the right layer

All Dart code in a Flutter app runs on the UI isolate unless you move it.
Anything synchronous that takes more than a few milliseconds there (decoding
a large JSON list, parsing CSV or XML, hashing, image processing, sorting
tens of thousands of items, regex over a big document) drops frames, because
the isolate can't build the next frame until it's done.

## Contents

1. When to reach for an isolate
2. `Isolate.run` vs `compute` vs a long-lived isolate
3. Where the isolate call lives in each architecture
4. What to send (and what never to send)
5. Pitfalls

## 1. When to reach for an isolate

- **DO measure first.** In the DevTools Performance view (profile mode), a
  long UI-thread frame with your parse or compute function in the CPU
  profile is the signal. Small payloads (a few KB) cost more to send to an
  isolate than to parse inline.
- **DO move** JSON lists of unknown or large size (the docs.flutter.dev
  cookbook "Parse JSON in the background"), file parsing, crypto and hashing
  of big inputs, image transforms, search indexing and diffing.
- **AVOID isolates for I/O.** `http`, `dio`, file and database calls are
  already asynchronous. Only the CPU-bound part afterwards needs to move.
  Drift and some other databases can already run their queries on a
  background isolate (for example Drift's `NativeDatabase.createInBackground`).

## 2. `Isolate.run` vs `compute` vs a long-lived isolate

| Tool | Use it for |
|---|---|
| `Isolate.run(() => work(input))` (Dart 2.19+) | one-off jobs; the result comes back without an extra copy |
| `compute(work, input)` (flutter/foundation) | the same, with a top-level or static function; on the web it runs inline |
| a long-lived isolate with `SendPort`/`ReceivePort` | repeated jobs with warm state (a search index, a parser with a big table) |

Background isolates that call plugins need
`BackgroundIsolateBinaryMessenger.ensureInitialized(rootIsolateToken)`
first, and only plugins that support background isolates work there.

## 3. Where the isolate call lives in each architecture

The rule in every pattern: **the layer that owns the raw data does the
heavy transform**. Callers just await a `Future`. Widgets never spawn
isolates.

| Pattern | Put `Isolate.run`/`compute` in | Never in |
|---|---|---|
| MVN (Clean + Riverpod) | the data source or repository impl (parse the DTO list); a use case only when the heavy work is domain logic | the notifier, the view |
| MVVM (Flutter guide) | the service (API client) or repository | the view model's `Command`, the view |
| Bloc / Cubit | the data provider (API client) or repository | the bloc's event handler, the widget |
| Clean Architecture | data layer (source → DTO → entity mapping) | domain entities, presentation |
| Provider | the service the `ChangeNotifier` calls | the model's `notifyListeners` path, the widget |
| GetX | the provider / repository (or a `GetConnect` decoder) | the `GetxController`, the view |
| Riverpod (plain) | the repository, behind the provider that exposes it | a provider's `build` body directly, the widget |
| setState | a plain service function the `State` awaits | `build`, `initState` bodies |

```dart
// Data source: transport + parse; nothing above this knows an isolate exists
class PostsRemoteSource {
  PostsRemoteSource(this._client);
  final http.Client _client;

  Future<List<PostDto>> fetchPosts() async {
    final res = await _client.get(Uri.https('api.example.com', '/posts'));
    if (res.statusCode != 200) throw HttpStatusException(res.statusCode);
    final body = res.body;                                   // send the String, not the response
    return Isolate.run(() => parsePosts(body));
  }
}

List<PostDto> parsePosts(String body) =>
    (jsonDecode(body) as List).map((j) => PostDto.fromJson(j as Map<String, dynamic>)).toList();
```

## 4. What to send (and what never to send)

- **DO send the minimum:** the response body (`String`/`Uint8List`), a file
  path, the parameters of the computation. Messages are copied, so big
  objects cost a copy each way. `TransferableTypedData` moves bytes without
  copying.
- **DON'T send tokens, API keys, cookies or the HTTP client** to an isolate
  that only parses. A closure passed to `Isolate.run` captures every variable
  it references. Build the closure from local values (`final body =
  res.body;`), not from `this`, or you ship the repository (and its secrets)
  across.
- **DON'T log payloads from isolates or hot paths.** A `print` of a parsed
  user list in a parser runs for every page and puts PII in the device log
  (SEC-004 in `flutter-secure-defaults`). Log counts and durations instead.
- **DO map errors on the way back.** An exception thrown in `Isolate.run`
  is rethrown in the caller. Catch and map it in the repository like any
  other `FormatException` (`flutter-error-handling`, ERR-004).

## 5. Pitfalls

- A closure that captures `this` (a repository with a Dio instance, a
  `BuildContext`) fails to send, or sends far more than intended.
- `compute` on the web runs on the main thread. Keep payloads small there, or
  use a web worker.
- Spawning an isolate per list item or per keystroke costs more than the
  work. Batch, or keep one long-lived isolate.
- `debugPrint` throttles output, but string-building in hot paths still
  costs. Guard diagnostics with `kDebugMode`.
