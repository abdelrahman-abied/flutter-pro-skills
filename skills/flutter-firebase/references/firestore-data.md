# Firestore data: types, queries, listeners, writes, offline, cost

Everything here lives in the data source and the repository
(`placement-by-architecture.md`). Logic and views only see entities and
failures.

## Contents

1. Typed documents: `withConverter` or DTOs
2. Bounded queries and pagination
3. Listeners and their lifetime
4. Transactions and batched writes
5. Offline cache and pending writes
6. Indexes
7. Cost checklist

## 1. Typed documents: `withConverter` or DTOs

Type the document at the source boundary, once, so no `Map<String,
dynamic>` or `data()!['field'] as String` reaches the repository's callers.

```dart
class PostDto {
  PostDto({required this.id, required this.authorId, required this.text, required this.createdAt});

  final String id;
  final String authorId;
  final String text;
  final DateTime createdAt;

  factory PostDto.fromFirestore(DocumentSnapshot<Map<String, dynamic>> snap) {
    final d = snap.data();
    final text = d?['text'];
    final authorId = d?['authorId'];
    final ts = d?['createdAt'];
    if (text is! String || authorId is! String || ts is! Timestamp) {
      throw FormatException('post ${snap.id} is malformed');   // the repository maps it to a failure
    }
    return PostDto(id: snap.id, authorId: authorId, text: text, createdAt: ts.toDate());
  }

  Map<String, Object?> toFirestore() => {
        'authorId': authorId,
        'text': text,
        'createdAt': FieldValue.serverTimestamp(),
      };

  Post toEntity() => Post(id: id, text: text, createdAt: createdAt);
}

final posts = db.collection('posts').withConverter<PostDto>(
      fromFirestore: (snap, _) => PostDto.fromFirestore(snap),
      toFirestore: (dto, _) => dto.toFirestore(),
    );
```

- Validate in `fromFirestore`: documents are written by clients and older
  app versions, so a field can be missing or of another type. Treat the data
  as untrusted input, the same as an HTTP response.
- Use `FieldValue.serverTimestamp()` for times the server should decide;
  read them as `Timestamp?` because the local write has no value yet
  (`ServerTimestampBehavior.estimate` in `SnapshotOptions` if the UI needs
  one).
- `freezed` / `json_serializable` DTOs work too; keep a `Timestamp` ↔
  `DateTime` converter in the DTO, not in the entity.

## 2. Bounded queries and pagination

```dart
Future<Page<PostDto>> page({DocumentSnapshot<PostDto>? after, int size = 20}) async {
  Query<PostDto> q = posts.orderBy('createdAt', descending: true).limit(size);
  if (after != null) q = q.startAfterDocument(after);
  final snap = await q.get();
  return Page(items: [for (final d in snap.docs) d.data()], cursor: snap.docs.isEmpty ? null : snap.docs.last);
}
```

- Every list query has a `limit` (FIRE-007). Use `count()` for totals
  (`(await q.count().get()).count`) instead of fetching documents to count
  them, and `limit(1)` when you only need the first match.
- Keep the cursor (`DocumentSnapshot` or the last `orderBy` values) in the
  repository or the source; logic asks for "next page" and gets entities.
- Guard against duplicate page loads in logic (an in-flight flag, a Bloc
  `droppable` transformer), as for HTTP pagination (`flutter-networking`,
  NET-005).
- In the UI, `FirestoreListView` / `FirestoreQueryBuilder` from
  `firebase_ui_firestore` page a query for you; give them a `Query` built by
  the source (passed through the repository as an opaque handle only if the
  project accepts that coupling; otherwise page through the repository).
- `where` on one field plus `orderBy` on another needs a composite index
  (section 6).

## 3. Listeners and their lifetime

A listener is a subscription Firestore bills for: one read per document in
the first result, one per changed document after that, and the full result
again after a disconnect of more than 30 minutes.

| Owner | How it ends |
|---|---|
| Riverpod / MVN | return the stream from a `StreamProvider` / `StreamNotifier.build`; or `ref.onDispose(sub.cancel)` |
| Bloc | `emit.forEach` / `emit.onEach` in a handler; or store it and cancel in `close()` |
| MVVM, Provider | store it, cancel in `dispose()` |
| GetX | `bindStream`, or store it and cancel in `onClose()` |
| `State` | `StreamBuilder`; or store it in `initState`, cancel in `dispose()` |

- A discarded `listen(...)` result in any of those owners is FIRE-008.
- Re-subscribe when the key changes (a different `uid`): Riverpod families
  and Bloc events do it; a manual listener must cancel the old one first.
- Sign-out: cancel user-scoped listeners before or when auth changes;
  otherwise they fail with `permission-denied` once the rules see no user.
- `includeMetadataChanges: true` doubles callbacks (pending → committed);
  ask for it only when the UI shows pending state.

## 4. Transactions and batched writes

```dart
Future<void> like(String postId, String uid) => db.runTransaction((tx) async {
      final postRef = db.collection('posts').doc(postId);
      final likeRef = postRef.collection('likes').doc(uid);
      final like = await tx.get(likeRef);
      if (like.exists) return;
      tx.set(likeRef, {'at': FieldValue.serverTimestamp()});
      tx.update(postRef, {'likes': FieldValue.increment(1)});
    });
```

- Read-modify-write goes in `runTransaction`: reads first, then writes. The
  body can run several times on contention, so keep it free of side effects
  (no navigation, analytics or `setState`; FIRE-transaction-side-effects).
- Simple counters can use `FieldValue.increment` without a transaction.
- Several independent writes that must land together go in a `WriteBatch`
  (`db.batch()`, at most 500 operations; split larger loops,
  FIRE-batch-over-limit).
- Transactions fail offline; batches queue offline. Map
  `FirebaseException(code: 'aborted' | 'unavailable')` to a retryable failure.
- The rules still apply to each write in a transaction or batch.

## 5. Offline cache and pending writes

- Mobile and desktop SDKs cache by default; the web needs persistence turned
  on (`Settings(persistenceEnabled: true)`). Set `Settings` once, in the
  composition root, before the first query.
- A write resolves locally first: `await doc.set(...)` completes when the
  server acknowledges, which never happens offline, so don't block the UI on
  it. Fire the write, show the optimistic state, and surface
  `snap.metadata.hasPendingWrites` if the user needs to know.
- `snap.metadata.isFromCache` tells you a result may be stale. Decide per
  screen whether stale data is acceptable; `GetOptions(source:
  Source.server)` forces a round trip.
- Cache size, eviction and anything beyond Firestore's own cache (your own
  Drift or Hive tables, sync queues) belong to `flutter-persistence`.
- Sign-out on a shared device: `await FirebaseFirestore.instance.terminate();
  await FirebaseFirestore.instance.clearPersistence();` removes the previous
  user's cached documents (`flutter-secure-defaults`, logout wipe).

## 6. Indexes

- Single-field indexes are automatic. A query with equality on one field and
  `orderBy`/range on another, or `array-contains` plus `orderBy`, needs a
  composite index; without it the query fails with `failed-precondition`
  and a console link.
- Keep `firestore.indexes.json` in the repo (`firebase
  firestore:indexes > firestore.indexes.json`) and deploy it with the rules,
  so production has the index before the app ships (FIRE-index-not-committed).
- Exempt large, unqueried fields (long text, big arrays) with
  `fieldOverrides` to save index storage and write cost.

## 7. Cost checklist

- Every query: `limit`, or a `count()` aggregate.
- Every listener: one owner, cancelled with it; no duplicate listeners for
  the same query in several widgets (share it through the logic layer).
- Prefer `get()` for data that doesn't change while the screen is open.
- Denormalise what a list needs into the list documents instead of one
  extra read per row.
- Large reads (exports, admin tools) belong in a Cloud Function, not the
  client.
