# flutter-networking: review checklist and finding examples

Moved out of `SKILL.md` so writing code doesn't load it: read this file
when you review code in this area, or when `dart-flutter-review` sends
you here. Paths are relative to the skill folder.

## REVIEW checklist

Script rules (`NET-0xx`, full detail in `references/rules.md`):

| ID | Name | Default severity | What it catches |
|---|---|---|---|
| NET-001 | client-without-timeouts | Medium (Low when one is missing, or for a dart:io `HttpClient`) | `Dio()` / `BaseOptions` without `connectTimeout` and `receiveTimeout` |
| NET-002 | client-created-per-call | Medium (Low in an interceptor) | `Dio(` built inside a data-layer method instead of injected |
| NET-003 | http-client-never-closed | Low | a local `http.Client` / `HttpClient` / `IOClient` never closed or handed on |
| NET-004 | retry-resends-any-method | Medium | an interceptor's `onError` re-sends `requestOptions` with no method check |
| NET-005 | page-fetch-without-guard | Medium (Low when not scroll-triggered) | Bloc `on<…NextPage…>` without a transformer, or `loadMore()` with no in-flight check |
| NET-006 | cancel-token-never-cancelled | Low | a `CancelToken` nobody cancels, or one created inline |
| NET-007 | websocket-never-closed | Medium | a WebSocket channel never closed in its file |
| NET-008 | base-url-duplicated | Low | the same API host as a literal in several files |
| NET-009 | top-level-http-call | Low | `http.get(` / `http.post(` in a data-layer class |
| NET-010 | query-value-not-encoded | Low | text interpolated after `?q=` in an HTTP URL |

Reading-level findings (`NET-<slug>`; the checker can't see these):

| ID | Severity | Look for |
|---|---|---|
| NET-unvalidated-json | Medium | `fromJson` hard-casting nested server data with no check |
| NET-stale-response | Medium | an older search or filter response can overwrite a newer one |
| NET-retry-without-backoff | Medium | retries with no delay, cap or jitter, or retrying 4xx and parse errors |
| NET-websocket-reconnect-storm | Medium | reconnecting immediately on every close, forever |
| NET-upload-in-memory | Medium | a large file read into memory to upload, or a download buffered in memory |
| NET-no-cancellation | Low | requests that outlive their screen or provider, applied after it's gone |
| NET-interceptor-order | Low | logging before auth or retry |
| NET-no-fake-seam | Low | a client behind a static singleton that tests can't replace |

**Don't report here (cross-reference instead):**
- auth headers outside the data layer, token refresh: SEC-002 and
  `flutter-secure-defaults`; cleartext URLs: SEC-003; loggers and bodies in
  logs: SEC-005/011; accept-all certificates: SEC-006; pinning:
  `flutter-security-audit`; token storage: SEC-001
- clients or `http.get` in widgets, transport imports in views, logic or
  domain: ARCH-101/005/007/012/003; repositories returning `Response`, `Map`
  or DTOs: ARCH-107
- `DioException` escaping a repository: ERR-004; unguarded I/O in UI
  callbacks: ERR-014; retries of non-idempotent calls outside an interceptor:
  ERR-retry-non-idempotent (NET-004 beats it on the same line)
- large JSON decoded on the UI isolate: PERF-011
- cache policy, offline queues and their replay, connectivity treated as
  truth: `flutter-persistence` (PERSIST-no-cache-policy,
  PERSIST-non-idempotent-retry, PERSIST-connectivity-as-truth). The client's
  retry policy is NET's; replaying queued writes is PERSIST's.
- untrusted URL launches and PII in URLs: NAV-005/006

**When not to flag:**
- A small app or package on package:http with an injected `http.Client`
  (the bloc examples' API packages): that's the recommended seam.
- The Flutter compass sample's dart:io `HttpClient` created per request
  through an injected factory and closed in `finally`.
- A fresh client in a token-refresh interceptor that must bypass the auth
  interceptor (build it once if you can; otherwise suppress with a reason).
- A 401-gated replay after a refresh: the server rejected the request, so
  replaying it is safe.
- Casts in tutorial-sized `fromJson` code whose failure is caught and mapped.

## Finding examples

Use the suite's finding format (`dart-flutter-review` merges them):

```markdown
### [MEDIUM] Infinite list fetches the same page twice
- id: NET-005
- where: lib/features/feed/presentation/bloc/feed_bloc.dart:20
- evidence: `on<FeedNextPageRequested>(_onNextPage);` with no transformer; `_onScroll` adds the event on every scroll tick past 90%
- rule: Bloc: register the fetch with `transformer: droppable()` (flutter-networking › rules.md NET-005; bloclibrary infinite list)
- why: Bloc handles events concurrently by default, so two fetches start before `hasReachedMax` or the new items land; posts are appended twice
- fix: |
    on<FeedNextPageRequested>(_onNextPage, transformer: droppable());
- confidence: confirmed

### [MEDIUM] Retry interceptor re-sends POSTs
- id: NET-004
- where: lib/core/network/api_client.dart:20
- evidence: `handler.resolve(await _dio.fetch(err.requestOptions))` on any connection timeout
- rule: retry only idempotent methods (flutter-networking › rules.md NET-004)
- why: a POST /orders that timed out after the server committed it is placed again
- fix: |
    if (_isTransient(err) && _idempotent.contains(err.requestOptions.method)) { ... }
- confidence: confirmed
```

Open the report with one line naming the profile and the clients (`mvn, one
Dio client + web_socket_channel`). Report a pattern-wide issue (for example,
no client anywhere sets timeouts) **once**, with a few locations.
