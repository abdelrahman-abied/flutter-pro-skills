# Choosing storage

Pick the store by the shape of the data and how you read it, not by habit.
Most apps need two or three stores: settings in shared_preferences, secrets
in flutter_secure_storage, and one database for everything that is queried
or grows.

Official background: docs.flutter.dev's persistence cookbook ("Store
key-value data on disk", "Persist data with SQLite", "Read and write files")
and the architecture guide's design patterns for key-value data, SQL and
offline-first. If your agent has an official recipe installed (for example a
`flutter/agent-plugins` or `dart-lang/skills` persistence skill), follow it
for setup steps; this file adds the choice, the security defaults and the
review checks.

## Contents

1. The decision table
2. shared_preferences: small settings only
3. Relational databases: Drift and sqflite
4. Object and key-value stores: Hive, Isar, ObjectBox
5. Secrets: flutter_secure_storage
6. Files and caches on disk
7. Encryption at rest
8. Red flags in review

## 1. The decision table

| Data | Store | Why |
|---|---|---|
| theme, locale, onboarding seen, last tab, feature flags | shared_preferences (`SharedPreferencesAsync` / `SharedPreferencesWithCache`) | a handful of scalar values, read at startup |
| tokens, passwords, API keys, encryption keys | flutter_secure_storage | Keychain / Keystore; owned by `flutter-secure-defaults` |
| records you filter, sort, join, page or count; anything relational | **Drift** (typed queries, `watch()` streams, migrations with tests, web support) or sqflite (raw SQL, minimal) | SQL is the right tool once you query |
| documents or objects read by key, no joins, high write rate | Hive (hive_ce), Isar, ObjectBox | fast key/object access; weaker querying and migration tooling |
| an offline-first copy of server data | Drift (or another SQL store) as the local source of truth | streams + transactions + migrations |
| images, PDFs, exports, large blobs | files under `getApplicationSupportDirectory()`; the database holds the path | databases are bad at big blobs |
| HTTP response caching | the HTTP client's cache, or a table with `fetchedAt` | see `caching-and-offline.md` |

**PREFER Drift for new apps that store records.** It gives compile-time
checked queries, reactive `watch()` streams that repositories can expose
directly, transactions, a generated migration workflow
(`drift_dev make-migrations`) and schema tests. sqflite is fine for a few
tables and a team that wants raw SQL; it has no stream support and no
migration tests out of the box.

**AVOID starting new projects on unmaintained stores.** The original Hive and
Isar packages stopped receiving releases; their community forks (`hive_ce`,
`isar_community`) continue them. Check the package's pub.dev activity before
you choose, and keep the store behind a source so you can swap it.

## 2. shared_preferences: small settings only

- **DO** use it for small, non-sensitive scalars: booleans, enums stored as
  names, short strings.
- **DON'T** store tokens, passwords or personal data there (SEC-001). It is a
  plain XML file on Android and a plist on iOS, and both are included in
  device backups.
- **AVOID** storing lists of records, JSON blobs or growing histories
  (`PERSIST-prefs-as-database`). Every write rewrites the whole file, there's
  no query, no transaction and no migration story.
- **PREFER** the newer APIs (shared_preferences ≥ 2.3):
  - `SharedPreferencesAsync`: every call goes to the platform, no in-memory
    cache, so values are never stale across isolates or after a native write.
  - `SharedPreferencesWithCache`: a local cache with an `allowList` of keys you
    expect, created once at startup.
  - The legacy `SharedPreferences.getInstance()` keeps working but caches
    everything and is slated for deprecation (`PERSIST-legacy-prefs-api`, info).

```dart
// data/sources/settings_local_source.dart
class SettingsLocalSource {
  SettingsLocalSource(this._prefs);

  final SharedPreferencesWithCache _prefs;

  static Future<SettingsLocalSource> create() async => SettingsLocalSource(
        await SharedPreferencesWithCache.create(
          cacheOptions: const SharedPreferencesWithCacheOptions(
            allowList: {_kThemeMode, _kOnboarded},
          ),
        ),
      );

  static const _kThemeMode = 'settings.theme_mode';
  static const _kOnboarded = 'settings.onboarded';

  ThemeMode get themeMode =>
      ThemeMode.values.asNameMap()[_prefs.getString(_kThemeMode)] ?? ThemeMode.system;

  Future<void> setThemeMode(ThemeMode mode) => _prefs.setString(_kThemeMode, mode.name);
}
```

- **DO** namespace keys (`settings.theme_mode`) and keep them as constants in
  the source. A renamed key is a migration (`migrations.md` §4).

## 3. Relational databases: Drift and sqflite

**Drift**
- Tables are Dart classes (`class Notes extends Table`) or `.drift` files; the
  database is `@DriftDatabase(tables: [...]) class AppDatabase extends _$AppDatabase`.
- Open it with `driftDatabase(name: 'app')` from `drift_flutter`, which picks
  native or web and runs queries in a background isolate.
- Create **one instance** for the app and inject it (PERSIST-006).
- Queries are typed (`select(notes)..where((n) => n.done.equals(false))`).
  Use `customSelect` only with `variables:` (PERSIST-001).
- `watch()` / `watchSingleOrNull()` return streams that re-emit after any
  write through the same instance.
- Group writes in `transaction(() async {...})` or `batch((b) {...})`
  (PERSIST-007).

**sqflite**
- `openDatabase(path, version:, onCreate:, onUpgrade:)`; `onCreate` creates
  the latest schema, and `onUpgrade` migrates step by step (PERSIST-003).
- Always bind values: `rawQuery('… WHERE id = ?', [id])`,
  `query(table, where: 'id = ?', whereArgs: [id])` (PERSIST-001).
- `db.batch()` + `commit(noResult: true)` for bulk writes,
  `db.transaction((txn) async {...})` when steps depend on each other; inside
  a transaction use `txn`, never `db` (that deadlocks).
- It doesn't run on the web; `sqflite_common_ffi` covers desktop.

## 4. Object and key-value stores: Hive, Isar, ObjectBox

- **Hive (hive_ce):** boxes of key/value or typed objects with generated
  `TypeAdapter`s. `@HiveType(typeId:)` must be unique across the app
  (PERSIST-004), and `@HiveField(n)` indexes unique and never reused
  (PERSIST-005). Open boxes once (`Hive.openBox` returns the open box if it's
  already open) and keep `Box` references in the source. Encrypt sensitive
  boxes with `encryptionCipher` (PERSIST-009).
- **Isar / isar_community:** typed collections with indexes and queries; one
  `Isar.open(...)` per app (PERSIST-006); writes go in `writeTxn`.
- **ObjectBox:** fast object store with relations and queries; one `Store`
  per app (`openStore()` once).
- **All of them:** keep their annotated classes in `data/` (models or
  "entities" in the store's sense) and map them to domain entities in the
  repository. A `@HiveType` domain entity imports the store into the domain
  layer (ARCH-003).

## 5. Secrets: flutter_secure_storage

Secrets go in flutter_secure_storage behind a data-layer source, and that's
`flutter-secure-defaults`' territory: load it (or read
`../flutter-secure-defaults/SKILL.md` and `../flutter-secure-defaults/references/storage-and-privacy.md`).
Persistence code adds one duty: when you encrypt a database or a box, its key
is a secret. Generate it once (`Hive.generateSecureKey()`, or 32 bytes from
`Random.secure()`), keep it in secure storage, and never in source,
`--dart-define` or shared_preferences.

## 6. Files and caches on disk

- Private files go in `getApplicationSupportDirectory()` (not backed up to
  the user's Files app) or `getApplicationDocumentsDirectory()` (user
  documents). Caches you can rebuild go in `getTemporaryDirectory()` or
  `getApplicationCacheDirectory()`; the OS may clear them.
- **DON'T** put personal data in file names, box names or cache keys
  (`PERSIST-pii-in-key`). They show up in backups, logs and crash reports even
  when the contents are encrypted. Use an opaque id or a hash.
- Store the path in the database and the bytes in the file. Delete both
  together.

## 7. Encryption at rest

| Store | How | Key |
|---|---|---|
| Drift | SQLCipher via `sqlcipher_flutter_libs` (or SQLite3MultipleCiphers, see drift's encryption docs), then `PRAGMA key` in the database `setup` callback | 32 random bytes in flutter_secure_storage |
| sqflite | `sqflite_sqlcipher` with `password:` | same |
| Hive | `encryptionCipher: HiveAesCipher(key)` on each sensitive box | `Hive.generateSecureKey()`, stored in secure storage |
| Isar / ObjectBox | check the package's current encryption support; if none, keep sensitive fields out or encrypt them before storing | same |
| files | encrypt before writing (e.g. AES-GCM from `cryptography`) | same |

**DO** encrypt health, identity, card, bank and similar data (PERSIST-009),
and anything your privacy policy calls sensitive. **CONSIDER** whether the data
needs to be on the device at all; often a server-side copy plus a short-lived
in-memory cache is the safer design.

`PRAGMA key` can't use bound parameters. Escape the key (`replaceAll("'",
"''")`) or pass it as a hex blob (`PRAGMA key = "x'…'"`), and never log the
statement.

## 8. Red flags in review

- A list of records or a JSON blob in shared_preferences.
- Two different stores holding the same entity with no rule for which wins
  (`AP-two-sources-of-truth`).
- A token or password in any store other than secure storage (SEC-001).
- Health, identity or card data in an unencrypted box or database (PERSIST-009).
- A database or box opened in a widget (ARCH-101) or created per call (PERSIST-006).
- No plan for the next schema change (PERSIST-002/003, `migrations.md`).
