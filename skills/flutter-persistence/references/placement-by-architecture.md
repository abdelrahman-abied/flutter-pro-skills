# Placement by architecture

Every pattern in the suite agrees on the persistence shape: the store lives
in a **local source** (MVN, Clean), **service** (Flutter MVVM) or **data
provider** (Bloc) in the data layer; the **repository** owns the cache policy
and merges remote and local; and the **logic layer never knows which store
holds the data**. What differs is the naming, who calls the repository, and
how the single database instance is injected.

Detect the pattern first: run `../flutter-architecture/scripts/arch_check.py
<project-root> --json`, or read the project (§3 precedence of the suite: the
project's declared convention wins). The background for the repository rules
is `../flutter-architecture/references/repository-pattern.md`.

## Contents

1. The shape every pattern shares
2. One database instance, injected
3. Rows, DTOs and entities
4. Per pattern: MVN, MVVM, Bloc/Cubit, Clean, Provider, GetX, Riverpod
5. Logout and account switch
6. Reactive queries (watch streams)
7. Testing seams

## 1. The shape every pattern shares

```
view ──► logic (notifier / view model / bloc / controller)
              │   asks for domain objects, never for "the cache"
              ▼
         repository  ── owns: cache policy, staleness, merge, sync, error mapping
          │      │
          ▼      ▼
   remote source   local source (Drift DAO / sqflite / Hive box / prefs)
          │              │
        DTOs          rows / table classes / Hive models
```

- **DO** keep every storage package import in `data/` (ARCH-005/007/012 report
  leaks into UI and logic; ARCH-003 into domain).
- **DO** let the repository decide freshness ("is the cached copy older than
  10 minutes?"). The logic layer may pass intent (`refresh: true`), never a
  store choice (`fromCache: true`).
- **DO** map rows and DTOs to domain entities inside the repository. Logic and
  views never see a drift row, a companion or a `HiveObject`
  (`PERSIST-persistence-type-leak`).
- **AVOID** one repository per store (`NotesCacheRepository` +
  `NotesApiRepository`). One repository per type of data, with two sources.

## 2. One database instance, injected

A database is a process-wide resource. Create it once in the composition
root, close it on shutdown, and pass it to sources (PERSIST-006).

| DI style | One instance |
|---|---|
| Riverpod (codegen) | `@Riverpod(keepAlive: true) AppDatabase appDatabase(Ref ref) { final db = AppDatabase(driftDatabase(name: 'app')); ref.onDispose(db.close); return db; }` |
| Riverpod (classic) | `final appDatabaseProvider = Provider<AppDatabase>((ref) { … ref.onDispose(db.close); return db; });` (not `.autoDispose`) |
| Provider | `Provider<AppDatabase>(create: (_) => AppDatabase(…), dispose: (_, db) => db.close(), child: …)` at the root |
| Bloc | build the data provider in `main()` / `bootstrap()` and pass it to the repository, which `RepositoryProvider.value` exposes |
| get_it | `getIt.registerLazySingleton<AppDatabase>(() => AppDatabase(…), dispose: (db) => db.close())` (never `registerFactory`) |
| GetX | `Get.put<AppDatabase>(AppDatabase(…), permanent: true)` or a `GetxService` in an initial binding |
| setState / none | a field created in `main()` and passed down through constructors |

Background isolates (WorkManager, `flutter_background_service`, a
`compute` worker that writes) are the exception: they have their own memory,
so they open their own connection. With drift, prefer
`driftDatabase(name: …, native: const DriftNativeOptions(shareAcrossIsolates: true))`,
or `DriftIsolate` / `computeWithDatabase`, so the isolates share one
connection instead of fighting over the file.

## 3. Rows, DTOs and entities

```dart
// data/sources/notes_local_source.dart   (Drift DAO)
@DriftAccessor(tables: [Notes])
class NotesDao extends DatabaseAccessor<AppDatabase> with _$NotesDaoMixin {
  NotesDao(super.db);

  Stream<List<NoteRow>> watchOpen() =>
      (select(notes)..where((n) => n.archived.equals(false))).watch();

  Future<void> upsertAll(List<NotesCompanion> rows) =>
      batch((b) => b.insertAllOnConflictUpdate(notes, rows));
}

// data/models/note_mappers.dart
extension NoteRowX on NoteRow {
  Note toEntity() => Note(id: NoteId(id), title: title, updatedAt: updatedAt);
}

extension NoteDtoX on NoteDto {
  NotesCompanion toCompanion() => NotesCompanion.insert(
        id: Value(id), title: title, updatedAt: DateTime.parse(updatedAt));
}
```

- Name rows so they can't be mistaken for entities: `@DataClassName('NoteRow')`
  on the table, or keep the drift default and name the entity differently.
- Mappers live in `data/` (next to the DTOs). The domain entity has no
  `toCompanion()`.
- Keep enum and date conversions in the table (`TypeConverter`s,
  `textEnum<T>()`) so the database holds stable values. Store enum **names**,
  not indexes; reordering an enum then can't corrupt data.

## 4. Per pattern

### MVN (Model-View-Notifier, Riverpod codegen)

```
features/notes/
  data/
    sources/notes_local_source.dart        # wraps the DAO / box (+ its provider)
    sources/notes_remote_source.dart
    models/note_dto.dart, note_mappers.dart
    repositories/notes_repository_impl.dart # cache policy + merge
  domain/
    entities/note.dart
    repositories/notes_repository.dart      # abstract interface class
    usecases/watch_notes_usecase.dart       # unchanged by any storage decision
  presentation/notifier/notes_notifier.dart
core/database/app_database.dart + app_database_provider.dart (keepAlive)
```

The notifier calls use cases (ARCH-012); the use case calls the repository
contract; only the impl and the sources know about drift. Swapping Hive for
drift changes `data/` only. Expose `Stream<List<Note>>` from the repository and
let a stream use case feed an `@riverpod Stream<List<Note>>` or the notifier's
`build()`.

### MVVM (Flutter architecture guide)

```
data/services/database_service.dart     # or local_notes_service.dart: wraps the DB
data/services/api_client.dart
data/repositories/notes/notes_repository.dart          # abstract
data/repositories/notes/notes_repository_local.dart    # or …_remote, …_offline_first
ui/notes/view_models/notes_view_model.dart             # unchanged
```

The guide's own offline-first pattern: the repository reads the local service
first, refreshes from the API, writes the result locally, and exposes the
local copy. View models call the repository through `Command`s and never see
the service. The guide's key-value and SQL design patterns place
`SharedPreferencesService` and `DatabaseService` exactly here.

### Bloc / Cubit (bloclibrary)

```
packages/notes_api/              # abstract data provider + models
packages/local_storage_notes_api/  # drift/Hive/prefs implementation
packages/notes_repository/       # combines providers, exposes Stream<List<Note>>
lib/notes/bloc/notes_bloc.dart   # unchanged
```

`flutter_todos` is the reference: `LocalStorageTodosApi` implements
`TodosApi`; `TodosRepository` wraps it; blocs subscribe to
`repository.getTodos()` with `emit.forEach`. Build the data provider in
`bootstrap()` and hand the repository to `RepositoryProvider`. HydratedBloc is
for small UI state that should survive a restart (filters, last tab), not a
database, and never for secrets.

### Clean Architecture

`data/datasources/local/notes_local_data_source.dart` (contract +
implementation), `data/models/` for rows and DTOs, `data/repositories/
notes_repository_impl.dart` doing the merge, `domain/` untouched. Use cases
that only forward a call are fine here (`AP-passthrough-usecase` is info).

### Provider (ChangeNotifier)

The `ChangeNotifier` calls a repository passed in its constructor; the
repository holds the database or box from a root `Provider`. No
`SharedPreferences.getInstance()` inside the notifier (ARCH-007).

### GetX

A `GetxService` (or a repository registered `permanent: true`) owns the
database; controllers get the repository with `Get.find` in their bindings.
Controllers don't open boxes in `onInit`.

### Plain Riverpod

Same as MVN without the use-case layer: `appDatabaseProvider` (keepAlive) →
`notesLocalSourceProvider` → `notesRepositoryProvider` →
`notesProvider` (`StreamProvider`/`AsyncNotifier`). Widgets watch only the
last one.

## 5. Logout and account switch

Logout wipes everything that belongs to the user. That's
`SEC-no-logout-wipe` in `flutter-secure-defaults`; the persistence side of the
list is:

- delete the user's rows or the whole database file (`db.close()` then delete
  the file, or `DELETE FROM` every user table in one transaction);
- `Hive.deleteBoxFromDisk(...)` for user boxes (or `box.clear()`);
- `SharedPreferencesAsync().clear(allowList: userKeys)` for user-scoped
  preferences (keep device-level settings such as theme if you want);
- the outbox (pending operations belong to the old session);
- image and HTTP caches holding private content;
- the in-memory caches in repositories (`ref.invalidate`, `reset()`,
  re-created blocs).

Put the wipe in one place (a `SessionRepository.signOut()` or a sign-out use
case) that calls each source's `clear()`, so a new store can't be forgotten.
For multi-account apps, name databases by an opaque account id
(`app_<uuid>.db`), never by email (`PERSIST-pii-in-key`).

## 6. Reactive queries (watch streams)

- Expose `Stream<List<Entity>>` from the repository (map inside it:
  `dao.watchOpen().map((rows) => rows.map((r) => r.toEntity()).toList())`).
- The logic layer subscribes the way its pattern prescribes: Riverpod
  `StreamProvider` / notifier `build()` returning a stream; Bloc
  `emit.forEach(repository.watchNotes(), onData: …)`; MVVM a
  `StreamSubscription` in the view model, cancelled in `dispose()`.
- Widgets never call `db.watch()` themselves (ARCH-101/005) and never create
  a stream in `build()` (`future-in-build`, UI-lifecycle).
- A `watch()` stream only sees writes through the same database instance,
  which is one more reason for PERSIST-006.

## 7. Testing seams

- Drift: `AppDatabase(NativeDatabase.memory())` in unit tests for the DAO and
  the repository; `SchemaVerifier` tests for migrations (`migrations.md` §1).
- sqflite: `sqflite_common_ffi` with `inMemoryDatabasePath`.
- Hive: `Hive.init(tempDir.path)` per test, deleted in `tearDown`.
- shared_preferences: `SharedPreferences.setMockInitialValues({})` for the
  legacy API; for the async APIs set `SharedPreferencesAsyncPlatform.instance =
  InMemorySharedPreferencesAsync.empty()` (from shared_preferences_platform_interface).
- Logic tests use a fake repository, not a database (see `flutter-testing`).
