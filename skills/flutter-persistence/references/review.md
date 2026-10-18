# flutter-persistence: review checklist and finding examples

Moved out of `SKILL.md` so writing code doesn't load it: read this file
when you review code in this area, or when `dart-flutter-review` sends
you here. Paths are relative to the skill folder.

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
