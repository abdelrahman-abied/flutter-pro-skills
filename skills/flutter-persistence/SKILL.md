---
name: flutter-persistence
description: Write and review Flutter local persistence, clean and secure by default and placed by the app's own architecture. Covers choosing storage (Drift or sqflite for relational data, Hive, Isar or ObjectBox for objects, shared_preferences for small settings, flutter_secure_storage for secrets), caching (cache-aside, TTL, stale-while-revalidate, invalidation), offline-first sync with an outbox, conflict rules, idempotency keys, schema migrations with tests, transactions and watch() streams, and where sources and repositories sit in MVN, MVVM, Bloc, Clean, Provider, GetX and Riverpod. Secures data with bound SQL parameters, encryption at rest and a logout wipe, and ships a checker. Use it whenever code touches a database, cache, Hive box, table, migration, schemaVersion or offline mode, even if nobody says "persistence". For tokens load flutter-secure-defaults, for layers flutter-architecture.
license: MIT
metadata:
  author: abdelrahman-abied
  version: "1.4.1"
  suite: flutter-pro-skills
---

# Flutter persistence

Local data outlives every release. A bad query crashes on the first
apostrophe, a missing migration bricks the database for every upgraded user,
a second database instance makes `watch()` streams go quiet, and an
unencrypted health box sits in plain text in every device backup. This skill
writes storage code that is correct for the architecture the project already
uses and safe without a later hardening pass.

The core split holds in every pattern:

- **The store lives in the data layer**: a local source (MVN, Clean), a
  service (Flutter MVVM) or a data provider (Bloc). Nothing above it imports
  drift, sqflite, Hive or shared_preferences.
- **The repository owns the policy**: cache freshness, merging remote and
  local, the outbox and sync, mapping rows to domain entities, and error
  mapping.
- **Logic never knows which store holds the data**: notifiers, view models,
  blocs and controllers ask the repository for domain objects and streams.
- **One database instance** per app, created in the composition root and
  injected.
- **Secure by default**: bound SQL parameters, sensitive data encrypted at
  rest, secrets only in secure storage, everything user-owned wiped on logout.

## Workflow

### 1. Detect the architecture and the stores

Check your agent's project instructions file (`AGENTS.md`, `CLAUDE.md`,
`GEMINI.md`, `.cursor/rules/…`, `.github/copilot-instructions.md`) for a
declared pattern or storage package. A declared convention wins. Then run the
checker. It is read-only, uses only the Python standard library, and doesn't
need `pub get`:

```bash
python3 -I <skill-dir>/scripts/check_persistence.py <project-root>                  # text report
python3 -I <skill-dir>/scripts/check_persistence.py <project-root> --json           # schema flutter-pro-skills/persistence@1
python3 -I <skill-dir>/scripts/check_persistence.py <project-root> --files changed.txt  # diff review
python3 -I <skill-dir>/scripts/check_persistence.py <project-root> --profile bloc   # declared pattern wins
```

The CLI is `check_persistence.py <project-root> [--json] [--files
<list-file-or-comma-list>] [--profile auto|mvn|mvvm|bloc|mvc|getx|provider|riverpod|setstate]
[--max n]`. It exits `0` whenever a report is produced and `2` on a usage
error. It reads the profile and file roles from the `flutter-architecture`
checker (`../flutter-architecture/scripts/arch_check.py --json`). If that
sibling is missing, it falls back to path-based detection and says so on the
`classification:` line.

```text
== PERSISTENCE
  profile: mvn + clean (arch_check, confidence high)
  classification: arch_check files[]
  scanned: 142 files; stores: drift, hive, sqflite; 6 SQL statements, 3 drift databases, 1 sqflite open, 2 Hive types
  [PERSIST-001] sql-built-from-strings (high) x1 — SQL text is built by interpolating ...
      lib/features/notes/data/sources/notes_local_source.dart:14  return _db.rawQuery("SELECT * FROM $kNotesTable WHERE title LIKE '%$query%'");   [`query` is a parameter of search, ...]
```

### 2. Choose the store, then place each piece by the pattern

Pick the store by the data's shape (`references/choosing-storage.md`):
settings → shared_preferences (`SharedPreferencesAsync` /
`SharedPreferencesWithCache`); records you query → Drift (or sqflite);
objects by key → Hive (hive_ce), Isar or ObjectBox; secrets →
flutter_secure_storage (owned by `flutter-secure-defaults`).

| Piece | MVN | MVVM | Bloc / Cubit | Clean | Provider | GetX | Riverpod |
|---|---|---|---|---|---|---|---|
| store wrapper | `data/sources/<x>_local_source.dart` | `data/services/<x>_service.dart` | data provider package (`local_storage_<x>_api`) | `data/datasources/local/` | `data/` source | service / source | source + its provider |
| cache policy, merge, outbox | repository impl | repository (`…_offline_first`) | repository package | repository impl | repository | repository | repository provider |
| row ↔ entity mapping | `data/models/` mappers | repository | repository | `data/models/` | repository | repository | repository |
| who reads it | use case → notifier | view model (`Command`) | bloc (`emit.forEach`) | use case | ChangeNotifier | controller | notifier / `StreamProvider` |
| one DB instance | `@Riverpod(keepAlive: true)` | root `Provider` / `MultiProvider` | built in `bootstrap()`, `RepositoryProvider` | DI module | root `Provider(create:, dispose:)` | `Get.put(permanent: true)` / `GetxService` | keepAlive provider |

Read `references/placement-by-architecture.md` for the full layouts, the
single-instance recipes per DI style, mappers, `watch()` streams and the
logout wipe. Read `references/caching-and-offline.md` before writing a cache,
an offline mode or a sync. Read `references/migrations.md` before any schema,
box or key change.

For step-by-step setup (adding drift and build_runner, configuring sqflite,
Hive initialisation), defer to the official docs.flutter.dev persistence
cookbook and, if your agent has them installed, the official
`flutter/agent-plugins` or `dart-lang/skills` recipes. This skill adds the
architecture placement, the security defaults and the review checks.

### 3. Write with the checklist below, then run the checker

Read the code behind every hit before calling it `confirmed`.
`references/rules.md` lists each rule's detection and its known false
positives. Suppress a deliberate case in the code, with a reason:
`// persist-ignore: PERSIST-001 column is checked against kSortColumns` (on
the reported line or the line above) or
`// persist-ignore-file: PERSIST-007 <reason>`.

## WRITE checklist

**Structure**
1. Keep every storage import in `data/` behind a source/service/data
   provider. The repository is the only caller (ARCH-005/007/012 report leaks).
2. Create one database instance in the composition root, close it on
   shutdown, and inject it. No `AppDatabase()` per call, per screen or in an
   auto-disposed provider (PERSIST-006).
3. Map rows, companions and Hive objects to domain entities in the
   repository. Logic and views never see a persistence type
   (`PERSIST-persistence-type-leak`).
4. Expose `Stream<…>` from the repository for data that changes (drift
   `watch()`), and let the logic subscribe the way its pattern prescribes.
5. Group writes that belong together in a transaction, and bulk writes in a
   batch (PERSIST-007). Never await the network inside a transaction.
6. State each repository method's read policy (cache-aside,
   stale-while-revalidate, network-first, local-only) and give every cache a
   TTL, invalidation on writes and a size bound (`PERSIST-no-cache-policy`).
7. Offline-first: the local database is the single source of truth; writes go
   to the local store and an outbox row in one transaction; sync runs from a
   data-layer service with backoff, idempotency keys and a written conflict
   policy. Connectivity is a hint, not a guarantee.

**Schema changes**
8. Drift: bump `schemaVersion` once per release, add a `stepByStep` step, run
   `dart run drift_dev make-migrations`, and keep the generated migration tests
   green (PERSIST-002/008).
9. sqflite: `onCreate` builds the latest schema, `onUpgrade` walks
   `if (oldVersion < N)` steps (PERSIST-003).
10. Hive: unique, never-reused `typeId`s and `@HiveField` indexes
    (PERSIST-004/005); renamed boxes and shared_preferences keys get a one-time
    migration behind a stored version.

**Secure by default**
11. Bind every value: `?` with `arguments`/`whereArgs` (sqflite),
    `variables: [Variable(...)]` or the typed query API (drift). Allow-list
    identifiers before interpolating them (PERSIST-001).
12. Tokens, passwords and keys live only in flutter_secure_storage (SEC-001,
    `flutter-secure-defaults`), including the key of an encrypted database or box.
13. Encrypt health, identity, card, bank and similar data at rest: SQLCipher
    for drift/sqflite, `encryptionCipher: HiveAesCipher(key)` for Hive
    (PERSIST-009). Better still, ask whether it needs to be on the device.
14. No personal data in cache keys, box names, database or file names
    (`PERSIST-pii-in-key`).
15. Logout and account switch wipe the user's database rows or file, boxes,
    user-scoped preferences, the outbox and private caches, from one sign-out
    path (SEC-no-logout-wipe).
16. Don't log SQL with values, rows or cache payloads (SEC-004 owns logging).
17. Backups: anything outside secure storage is in device backups unless
    excluded. For `android:allowBackup` and backup rules, defer to
    `flutter-security-audit` (STO-ALLOWBACKUP) if installed.

## REVIEW checklist

Script rules (`PERSIST-0xx`, full detail in `references/rules.md`):

| ID | Name | Default severity | What it catches |
|---|---|---|---|
| PERSIST-001 | sql-built-from-strings | High (Low when untraceable or constant-fed) | a value interpolated or concatenated into SQL (`rawQuery`, `customSelect`, `customStatement`, `execute`, sqflite `where:`) |
| PERSIST-002 | drift-schema-without-migration | High | `schemaVersion > 1` with no `migration` getter or no `onUpgrade` |
| PERSIST-003 | sqflite-version-without-upgrade | High | `openDatabase`/`OpenDatabaseOptions` with `version > 1` and no `onUpgrade` |
| PERSIST-004 | hive-type-id-collision | High | two adapters with the same `typeId` |
| PERSIST-005 | hive-field-index-collision | High | two `@HiveField(n)` with the same index in one type |
| PERSIST-006 | database-opened-per-use | Medium | a drift/Isar/ObjectBox database built per call, per screen, by an auto-disposed provider or by `registerFactory` |
| PERSIST-007 | writes-in-loop-without-transaction | Medium | awaited inserts/updates/deletes in a loop with no transaction or batch |
| PERSIST-008 | drift-migrations-untested | Low | a migrated drift database with no exported schemas and no `SchemaVerifier` test |
| PERSIST-009 | sensitive-store-unencrypted | Medium (Low for payment-like names) | health, identity, card or bank data in an unencrypted box, table or database |

Reading-level findings (`PERSIST-<slug>`; the checker can't see these):

| ID | Severity | Look for |
|---|---|---|
| PERSIST-destructive-migration | High | an upgrade that drops tables or deletes the file for data that isn't a rebuildable cache |
| PERSIST-offline-write-lost | High | an offline write that is dropped, or an optimistic update with no outbox and no rollback |
| PERSIST-persistence-type-leak | Medium | drift rows, companions or `HiveObject`s returned past the repository or used as UI state |
| PERSIST-no-cache-policy | Medium | a cache with no TTL, no invalidation and no size bound |
| PERSIST-sync-without-conflict-policy | Medium | two-way sync where whoever writes last silently wins |
| PERSIST-non-idempotent-retry | Medium | retried creates with no idempotency key in the offline replay queue (a retry interceptor in the HTTP client is `flutter-networking`'s `NET-004`) |
| PERSIST-key-rename-without-migration | Medium | a renamed preferences key, box or file with no read-old/write-new step |
| PERSIST-pii-in-key | Medium | emails, phones or names in cache keys, box or file names |
| PERSIST-prefs-as-database | Low | lists of records or JSON blobs in shared_preferences |
| PERSIST-connectivity-as-truth | Low | skipping requests or writes because `connectivity_plus` says offline |
| PERSIST-legacy-prefs-api | Info | new code on `SharedPreferences.getInstance()` instead of the async/cached APIs |

**Don't report here (cross-reference instead):**
- tokens or passwords in SharedPreferences, Hive or database columns: SEC-001;
  tokens in global or UI state: SEC-010; no logout wipe: SEC-no-logout-wipe
- `SharedPreferences.getInstance(` / `openDatabase(` in widgets: ARCH-101;
  storage imports in views, widgets or logic: ARCH-005/007/012; in the domain:
  ARCH-003; DTO imports and `Map` returns: ARCH-006/107
- swallowed or unmapped `SqliteException`/`HiveError`: ERR-001/002/004/007
- `allowBackup` and backup rules: `flutter-security-audit` STO-ALLOWBACKUP
- JSON decoding or heavy queries on the UI isolate: `flutter-performance`
- `watch()` subscriptions never cancelled: AP-stream-subscription-in-widget

**When not to flag:**
- A small app that keeps a few settings in shared_preferences behind a
  service: that's the Flutter guide's key-value pattern.
- bloclibrary's `LocalStorageTodosApi` storing the todo list as one JSON
  string: it's the tutorial's deliberate simplicity, and it sits behind the
  data-provider abstraction (mention `PERSIST-prefs-as-database` as Info only
  if the list will grow).
- A background isolate opening its own connection (prefer drift's
  `shareAcrossIsolates`).
- Interpolated constants, numbers, `'?'` placeholder lists and allow-listed
  identifiers in SQL.
- A destructive `onUpgrade` on a cache that's rebuilt from the server.

## Finding examples

Use the suite's finding format (`dart-flutter-review` merges them):

```markdown
### [HIGH] Search text is spliced into SQL
- id: PERSIST-001
- where: lib/features/notes/data/sources/notes_local_source.dart:14
- evidence: `_db.rawQuery("SELECT * FROM notes WHERE title LIKE '%$query%'")`, with `query` coming from the search field
- rule: bind every value (flutter-persistence › rules.md PERSIST-001)
- why: an apostrophe crashes the query, and `%' OR 1=1 --` returns every note
- fix: |
    _db.rawQuery('SELECT * FROM notes WHERE title LIKE ?', ['%$query%']);
- confidence: confirmed

### [HIGH] schemaVersion bumped without a migration
- id: PERSIST-002
- where: lib/core/database/app_database.dart:20
- evidence: `int get schemaVersion => 3;` and no `migration` getter
- rule: MVN: the database stays in core/database, the steps live with it; use cases are unchanged (migrations.md §1)
- why: drift's default onUpgrade throws, so every user upgrading from v2 gets a database that won't open
- fix: |
    dart run drift_dev make-migrations
    @override
    MigrationStrategy get migration => MigrationStrategy(onUpgrade: stepByStep(from2To3: (m, s) => m.createTable(s.tags)));
- confidence: confirmed
```

Open the report with one line naming the profile and the stores (`mvn,
drift + shared_preferences, no Hive`). Report a pattern-wide issue (for
example, no cache anywhere has a TTL) **once**, with a few locations.

## Related skills

These assume the suite is installed as sibling folders. If your agent doesn't
auto-load skills, read the path given. If a sibling is missing, carry on and
say which check you skipped.

- **`flutter-architecture`** for detecting the pattern and the layer rules
  (ARCH-003/005/007/012/101/107), and the repository pattern. Fallback:
  `../flutter-architecture/SKILL.md` and
  `../flutter-architecture/references/repository-pattern.md`.
- **`flutter-secure-defaults`** for tokens and secure storage (SEC-001/010),
  logging (SEC-004) and the logout wipe. Fallback:
  `../flutter-secure-defaults/SKILL.md`. **`flutter-security-audit`** (installed
  separately) for backups, Keychain settings and deep audits.
- **`flutter-error-handling`** for mapping `SqliteException`, `HiveError` and
  sync failures to typed failures (ERR-*). Fallback:
  `../flutter-error-handling/SKILL.md`.
- **`flutter-testing`** for repository tests over in-memory databases and
  fakes. Fallback: `../flutter-testing/SKILL.md`.
- **`flutter-feature-scaffold`** to generate a feature's source, repository and
  logic files in the project's pattern.
- **`flutter-performance`** for isolates, large decodes and list rendering
  of query results.
- **`dart-flutter-review`** merges PERSIST findings into its report.

## References

| File | Read it when |
|---|---|
| `references/choosing-storage.md` | choosing between shared_preferences, Drift, sqflite, Hive, Isar, ObjectBox, secure storage and files; encryption at rest |
| `references/placement-by-architecture.md` | deciding where the store, mappers, cache policy and the single database instance go in MVN, MVVM, Bloc/Cubit, Clean, Provider, GetX or Riverpod; watch streams; logout wipe |
| `references/caching-and-offline.md` | writing a cache (TTL, stale-while-revalidate, invalidation, bounds), offline-first reads, the outbox, retries, idempotency, conflicts |
| `references/migrations.md` | changing a drift or sqflite schema, Hive types, preference keys or file names; transactions and batches; migration tests |
| `references/rules.md` | every PERSIST rule: detection, why, fix, false positives; the reading-level slugs; what's checked elsewhere; calibration |
