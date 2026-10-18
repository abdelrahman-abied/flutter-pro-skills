---
name: flutter-networking
description: Write and review the API layer of Flutter and Dart apps, clean and secure by default and placed by the app's own architecture. Covers one configured client (Dio, http, retrofit, chopper, generated OpenAPI) injected via Riverpod, get_it or constructors, timeouts, interceptor order, remote sources, DTOs and JSON (json_serializable, freezed, validated fromJson), DTO to entity mapping, pagination with an in-flight guard, CancelToken and close() tied to the owner, idempotent-only retry with backoff, upload progress, WebSockets and fake clients in tests. Ships a NET checker. Use it whenever code calls an API, builds a Dio or http client, adds an interceptor, endpoint, DTO, fromJson, infinite scroll, WebSocket or upload, even if nobody says "networking". For tokens and auth load flutter-secure-defaults, for error mapping flutter-error-handling, for caching and offline flutter-persistence.
license: MIT
metadata:
  author: abdelrahman-abied
  version: "1.5.0"
  suite: flutter-pro-skills
---

# Flutter networking

Most API bugs aren't in the request itself. A `Dio()` with no timeouts hangs
a spinner forever on a dead network, a client built per call skips the auth
interceptor, a scroll listener fetches page 3 twice, a retry interceptor
places the same order twice, and a WebSocket keeps streaming to a screen that
closed an hour ago. This skill writes API code that is correct for the
architecture the project already uses and safe without a later hardening pass.

The core split holds in every pattern:

- **One configured client per backend**, built in the composition root and
  injected: base URL, timeouts, interceptors and logging policy live there.
- **A remote source per resource** in `data/` wraps the client. Nothing above
  the data layer imports `dio`, `http` or a DTO.
- **The repository maps** DTOs to entities and transport errors to failures.
  MVN use cases, MVVM view models and blocs never see a client or a DTO.
- **The logic holder owns request lifetimes**: the in-flight guard for "load
  more", the `CancelToken`, the socket subscription, each tied to its own
  dispose hook.
- **Secure by default**: timeouts set, HTTPS only, retries only for idempotent
  requests, server data validated at the DTO boundary, never trusted.

## Workflow

### 1. Detect the architecture and the clients

Check your agent's project instructions file (`AGENTS.md`, `CLAUDE.md`,
`GEMINI.md`, `.cursor/rules/…`, `.github/copilot-instructions.md`) for a
declared pattern or client package. A declared convention wins. Then run the
checker. It is read-only, uses only the Python standard library, and doesn't
need `pub get`:

```bash
python3 -I <skill-dir>/scripts/check_networking.py <project-root>                   # text report
python3 -I <skill-dir>/scripts/check_networking.py <project-root> --json            # schema flutter-pro-skills/networking@1
python3 -I <skill-dir>/scripts/check_networking.py <project-root> --files changed.txt  # diff review
python3 -I <skill-dir>/scripts/check_networking.py <project-root> --profile bloc    # declared pattern wins
```

The CLI is `check_networking.py <project-root> [--json] [--files
<list-file-or-comma-list>] [--profile auto|mvn|mvvm|bloc|mvc|getx|provider|riverpod|setstate]
[--max n]`. It exits `0` whenever a report is produced and `2` on a usage
error. It reads the profile and file roles from the `flutter-architecture`
checker (`../flutter-architecture/scripts/arch_check.py --json`, or
`$FPS_ARCH_JSON` when the review already ran it). If that sibling is missing,
it falls back to path-based detection and says so on the `classification:`
line.

```text
== NETWORKING
  profile: mvn + clean (arch_check, confidence high)
  classification: arch_check files[]
  scanned: 96 files; packages: dio, web_socket_channel; 2 Dio clients, 0 http clients, 2 interceptors, 1 WebSocket, 3 CancelTokens, 2 page handlers
  [NET-005] page-fetch-without-guard (medium) x1 — A "load the next page" handler awaits the network with no in-flight guard. ...
      lib/features/catalog/presentation/notifier/catalog_notifier.dart:15  Future<void> loadMore() async {   [loadMore() awaits the next page with no in-flight check before the await. Triggered from a scroll callback at ...]
```

### 2. Place each piece by the pattern

| Piece | MVN | MVVM | Bloc / Cubit | Clean | Provider | GetX | Riverpod |
|---|---|---|---|---|---|---|---|
| shared client | `core/network`, `@Riverpod(keepAlive: true)` | built at the root, passed to the API service | built in `main`/`bootstrap` | DI module | root `Provider(create:, dispose:)` | permanent `GetConnect`/Dio in the initial binding | keepAlive provider |
| remote source | `data/sources/<x>_remote_source.dart` | `data/services/api/` | data-provider package (`<x>_api`) | `data/datasources/remote/` | `data/` service | provider/service | source + its provider |
| DTO ↔ entity, error mapping | repository impl | repository (`Result<T>`) | repository package | repository impl (`Either`) | repository | repository | repository provider |
| "load more" guard | notifier flag or page family | `Command0` | `transformer: droppable()` | the logic layer's | `_isLoading` | `RxBool` | notifier flag or family |
| cancel / close | `ref.onDispose` | `dispose()` | `close()` | the logic layer's | `dispose()` | `onClose()` | `ref.onDispose` |

Read `references/placement-by-architecture.md` for the layouts and lifetime
hooks, `references/client-setup.md` for the shared client per DI style,
interceptor order, timeouts and generated clients,
`references/dtos-and-json.md` before writing a DTO, and
`references/requests.md` for pagination, cancellation, retry, transfers and
WebSockets.

For step-by-step setup (adding Dio or http, json_serializable and
build_runner), defer to the docs.flutter.dev networking cookbook and, if your
agent has them installed, the official `flutter/agent-plugins` or
`dart-lang/skills` recipes. This skill adds the architecture placement, the
secure defaults and the review checks.

### 3. Write with the checklist below, then run the checker

Read the code behind every hit before calling it `confirmed`.
`references/rules.md` lists each rule's detection and its known false
positives. Suppress a deliberate case in the code, with a reason:
`// net-ignore: NET-002 isolated client for the refresh call` (on the
reported line or the line above) or `// net-ignore-file: NET-008 <reason>`.

## WRITE checklist

**Structure**
1. Build one client per backend in the composition root and inject it into
   remote sources by constructor or provider. No `Dio()` inside a method
   (NET-002), no top-level `http.get` in a source (NET-009).
2. One remote source per resource; it returns DTOs and throws transport
   exceptions. The repository maps DTOs to entities and errors to failures
   (load `flutter-error-handling` for the mapping; ERR-004 reports leaks).
3. Keep DTOs in `data/models/`. Domain and presentation never import them
   (ARCH-003/006), and repositories don't return them (ARCH-107).
4. Add interceptors as auth → retry → logging (`client-setup.md` §3). Auth
   and refresh details belong to `flutter-secure-defaults`.

**Requests**
5. Set `connectTimeout` and `receiveTimeout` on the shared client (NET-001);
   for package:http, `.timeout()` inside the client wrapper.
6. Guard every "load more" against concurrent calls with the pattern's own
   tool (NET-005): Bloc `droppable()`, a notifier flag checked before the
   await, an MVVM `Command`, a GetX `RxBool`.
7. Tie each `CancelToken` and socket to the lifetime of whoever started it:
   `ref.onDispose`, Bloc `close()`, `dispose()`, `onClose()` (NET-006/007).
   Treat a cancellation as "no result", never as an error to show.
8. Cancel or ignore stale responses when the query changes (Bloc
   `restartable()`, a family keyed by the query).
9. Upload from files and download to files, streamed, with progress
   callbacks mapped to a domain value (`requests.md` §5).
10. WebSockets: `wss://`, close on dispose, reconnect with backoff and
    jitter, resubscribe after reconnecting (`requests.md` §6).

**Data**
11. Parse into DTOs with json_serializable (`checked: true`) or freezed, or
    hand-written `fromJson` with Dart 3 patterns that throw `FormatException`
    (`dtos-and-json.md`). Map parse failures to a failure; never retry them.
12. Build query strings with `queryParameters`, never by interpolation
    (NET-010).
13. Decode large payloads off the UI isolate (`flutter-performance`,
    PERF-011).

**Secure by default**
14. HTTPS and WSS only (SEC-003); never accept every certificate (SEC-006);
    pinning is a `flutter-security-audit` decision.
15. Retry only transient failures of idempotent requests, with backoff and a
    cap; POST/PATCH only with an `Idempotency-Key` (NET-004).
16. Validate every response at the DTO boundary; unknown enum values fall
    back instead of crashing.
17. No tokens or personal data in URLs or query strings; no bodies or headers
    in logs, and loggers only in debug builds (SEC-005/011).
18. Keep the base URL in one per-flavor config value, never repeated across
    files (NET-008) and never with secrets in it.
19. Test against fake clients only (`testing-with-fakes.md`).

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

## Related skills

These assume the suite is installed as sibling folders. If your agent doesn't
auto-load skills, read the path given. If a sibling is missing, carry on and
say which check you skipped.

- **`flutter-secure-defaults`** for auth headers, token refresh, HTTPS,
  logging and certificate rules (SEC-001/002/003/005/006/011). Fallback:
  `../flutter-secure-defaults/SKILL.md` and
  `../flutter-secure-defaults/references/network-and-auth.md`.
  **`flutter-security-audit`** (installed separately) for pinning and deep
  audits.
- **`flutter-error-handling`** for mapping `DioException`, `SocketException`
  and parse errors to failures and showing them (ERR-*). Fallback:
  `../flutter-error-handling/SKILL.md`.
- **`flutter-persistence`** for caching responses, offline-first sync and
  the outbox. Fallback: `../flutter-persistence/SKILL.md`.
- **`flutter-architecture`** for detecting the pattern and the layer rules,
  and the repository pattern. Fallback: `../flutter-architecture/SKILL.md`
  and `../flutter-architecture/references/repository-pattern.md`.
- **`flutter-testing`** for which layer to test first and fakes versus mocks.
  Fallback: `../flutter-testing/SKILL.md`.
- **`flutter-performance`** for decoding off the UI isolate and list
  rendering. Fallback: `../flutter-performance/SKILL.md`.
- **`flutter-feature-scaffold`** to generate a feature's source, repository
  and logic files in the project's pattern.
- **`dart-flutter-review`** merges NET findings into its report.

## References

| File | Read it when |
|---|---|
| `references/client-setup.md` | choosing http, Dio, retrofit, chopper, GetConnect or a generated client; building the shared client per DI style; interceptor order; timeouts; base URLs per flavor |
| `references/placement-by-architecture.md` | deciding where the client, sources, DTOs, mapping, pagination state and lifetime hooks go in MVN, MVVM, Bloc/Cubit, Clean, Provider, GetX or Riverpod |
| `references/dtos-and-json.md` | writing DTOs with json_serializable or freezed, a validating `fromJson`, mapping to entities, parse errors, sending data |
| `references/requests.md` | pagination and the in-flight guard, cancellation, retry with backoff, connectivity, uploads and downloads with progress, WebSockets |
| `references/testing-with-fakes.md` | testing sources with `MockClient`, a Dio `HttpClientAdapter` fake or http_mock_adapter, and logic over fake repositories |
| `references/rules.md` | every NET rule: detection, why, fix, false positives; the reading-level slugs; what's checked elsewhere; calibration |
