# Caching and offline-first

A cache is a promise about staleness. An offline-first app is a promise that
the user's writes survive no network, a killed app and a retry storm. Both
promises are the **repository's** job in every pattern; logic and views only
see domain objects and a status.

The Flutter architecture guide's offline-first design pattern (docs.flutter.dev,
app-architecture/design-patterns/offline-first) is the canonical reference for
MVVM and works the same way in MVN, Bloc and Clean.

## Contents

1. Pick a read policy
2. Staleness, invalidation and size bounds
3. Local database as the single source of truth
4. Offline writes: the outbox
5. Sync: retries, idempotency and conflicts
6. Connectivity is a hint
7. Review checklist

## 1. Pick a read policy

| Policy | Read path | Use when |
|---|---|---|
| **cache-aside** (read-through) | local hit and fresh → return; else fetch, store, return | data that changes rarely (catalogue, profile) |
| **stale-while-revalidate** | emit local immediately, fetch in the background, store, emit again | feeds and lists where showing something now beats showing the latest |
| **network-first, cache fallback** | fetch; on failure return the cached copy marked stale | data that must be current when possible (balances, stock) |
| **local-only + background sync** | always read local; sync jobs fill it | offline-first apps (notes, field work, chat history) |

Say which one each repository method uses in a doc comment. Mixing them
silently is how a screen ends up showing yesterday's price.

```dart
// MVVM / MVN / Bloc alike: inside the repository impl
Stream<List<Note>> watchNotes() async* {
  // stale-while-revalidate over a drift source
  unawaited(_refreshIfStale());
  yield* _local.watchAll().map((rows) => rows.map((r) => r.toEntity()).toList());
}

Future<void> _refreshIfStale() async {
  final fetchedAt = await _local.lastFetchedAt();
  if (fetchedAt != null && _clock.now().difference(fetchedAt) < _ttl) return;
  try {
    final dtos = await _remote.fetchNotes();
    await _local.replaceAll(dtos.map((d) => d.toCompanion()).toList(), fetchedAt: _clock.now());
  } on NetworkException catch (e, st) {
    _log.warning('notes refresh failed', e, st);   // the cached copy keeps being served
  }
}
```

Inject the clock (`DateTime Function() now` or `package:clock`) so TTL logic is
testable.

## 2. Staleness, invalidation and size bounds

- **DO** store `fetchedAt` (per row, per query key or per collection) and
  decide freshness in the repository with a named TTL constant.
- **DO** invalidate in the same repository that writes: after a successful
  `updateNote`, update or delete the cached row. Never let a screen "refresh
  the cache" by poking a second store (`AP-two-sources-of-truth`).
- **DO** bound every cache (`PERSIST-no-cache-policy`): an LRU of N entries
  for memory caches, a row cap or an age-based `DELETE … WHERE fetched_at < ?`
  run at startup for database caches, and the platform cache directory for
  files. lichess, for example, deletes rows older than a per-table TTL in
  `onOpen`, inside one transaction.
- **DO** key caches by stable, non-personal values: an opaque user id plus
  the query parameters, never an email or phone number (`PERSIST-pii-in-key`).
- **DO** clear user caches on logout and account switch
  (`placement-by-architecture.md` §5).
- **AVOID** caching authenticated responses in a shared HTTP cache without
  the user id in the key.
- **CONSIDER** an in-memory cache first (`Map` in the repository, as Compass
  does with `_cachedDestinations`). Persist only what must survive a restart.

## 3. Local database as the single source of truth

For offline-first, the UI reads **only** from the local store; the network
only writes into it.

```
remote ──sync──► local DB ──watch()──► repository stream ──► logic ──► view
                    ▲
user write ─────────┘ (local first, plus an outbox row, in one transaction)
```

- **DO** expose `watch…()` streams from the repository so writes from sync,
  from another screen or from a background isolate reach every listener.
- **DO** give every record a client-generated id (UUID v4/v7) so it exists
  before the server knows about it, and a `syncState` column (`synced`,
  `pending`, `failed`) when the UI needs to show it.
- **DON'T** keep a second in-memory list in the view model or bloc and
  "update both" (`AP-two-sources-of-truth`).

## 4. Offline writes: the outbox

An optimistic write that only lives in memory is lost when the app is killed
(`PERSIST-offline-write-lost`). Write the change and an outbox row in **one
transaction**, then let a sync worker drain the outbox.

```dart
// data/sources/notes_local_source.dart (drift)
Future<void> saveNoteOffline(NotesCompanion note) => _db.transaction(() async {
      await _db.into(_db.notes).insertOnConflictUpdate(note);
      await _db.into(_db.outbox).insert(OutboxCompanion.insert(
            id: _uuid.v4(),                    // doubles as the idempotency key
            entity: 'note',
            entityId: note.id.value,
            op: 'upsert',
            payload: jsonEncode(note.toJsonMap()),
            createdAt: _clock.now(),
          ));
    });
```

- One row per operation, applied in `createdAt` order per entity.
- Coalesce when it's safe (two edits of the same note → one upsert), never
  across a delete.
- The outbox belongs to the session: wipe it on logout.

## 5. Sync: retries, idempotency and conflicts

- **Retry with exponential backoff and jitter** (for example 1 s, 2 s, 4 s …
  capped at 5 min, ±20 %). Stop on 4xx errors other than 408/429 and mark the
  row `failed` so the UI can show it; retry 5xx, timeouts and network errors.
- **Idempotency keys** (`PERSIST-non-idempotent-retry`): send the outbox row id
  as `Idempotency-Key` (or in the body) so a retry after a lost response doesn't
  create a second order. Ask the backend to honour it; client-side alone isn't
  enough.
- **Delete the outbox row only after the server confirms**, inside the same
  transaction that writes the server's canonical version locally.
- **Conflict policy** (`PERSIST-sync-without-conflict-policy`) is a product
  decision. Pick one per entity and write it down:
  - *server wins*: simplest; the local edit is replaced and the user is told;
  - *last writer wins* by **server** timestamp or version (device clocks lie);
  - *field-level merge* for records edited in different fields;
  - *ask the user* for documents where a lost edit is expensive.
  Send the version you edited from (`If-Match`/`version`) so the server can
  detect the conflict.
- **Pull** with a cursor (`updatedSince`, a change token) and apply pages in a
  transaction; handle tombstones for server-side deletes.
- **Run sync from one place**: a sync service in the data layer, triggered at
  startup, on resume, after a local write and by a periodic background task
  (WorkManager / BGTaskScheduler). Never from a widget.

## 6. Connectivity is a hint

`connectivity_plus` tells you which network interface is up, not whether the
server is reachable: captive portals, VPNs, dead Wi-Fi and server outages all
report "connected" (`PERSIST-connectivity-as-truth`).

- **DO** try the request and treat a timeout or socket error as "offline".
- **DO** use connectivity changes only as a *trigger* to retry the outbox
  sooner.
- **DON'T** skip writes or block the UI because connectivity says "none";
  write locally and queue.

## 7. Review checklist

- [ ] Each repository method states its read policy.
- [ ] Every cache has a TTL or invalidation rule and a size bound.
- [ ] Cache keys and file names contain no personal data.
- [ ] Offline writes go to the local store and an outbox in one transaction.
- [ ] Retries back off, stop on permanent errors, and carry an idempotency key.
- [ ] There is a written conflict policy per synced entity.
- [ ] Sync runs from a data-layer service, not from widgets or blocs.
- [ ] Logout clears caches and the outbox.
