# Migrations, transactions and schema changes

A schema change ships to devices that already hold data. Fresh installs (and
your emulator) never run the migration, so a broken one surfaces only in
production, on real user data. Treat every version bump as code that needs a
test.

## Contents

1. Drift: schemaVersion, make-migrations, step-by-step, tests
2. sqflite: version and onUpgrade
3. Hive: type ids and field indexes
4. shared_preferences and file renames
5. Transactions and batches
6. Destructive changes
7. Release checklist

## 1. Drift

**Every schema change bumps `schemaVersion` and adds one step.** Drift's
default `onUpgrade` throws, so a bump without a strategy breaks every
upgraded install (PERSIST-002).

1. Tell drift_dev where the database is (`build.yaml`):

   ```yaml
   targets:
     $default:
       builders:
         drift_dev:
           options:
             databases:
               app_database: lib/core/database/app_database.dart
   ```

2. Before changing the schema, make sure the current version is exported:
   `dart run drift_dev make-migrations`. It writes
   `drift_schemas/app_database/drift_schema_vN.json`, generates
   `app_database.steps.dart` with typed snapshots of each version, and
   creates migration tests under `test/drift/app_database/`.
3. Change the tables, bump `schemaVersion`, and run `make-migrations` again.
4. Fill in the new step:

   ```dart
   @override
   int get schemaVersion => 3;

   @override
   MigrationStrategy get migration => MigrationStrategy(
         onCreate: (m) => m.createAll(),
         onUpgrade: stepByStep(
           from1To2: (m, schema) async {
             await m.addColumn(schema.notes, schema.notes.dueDate);
           },
           from2To3: (m, schema) async {
             await m.createTable(schema.tags);
             await m.alterTable(TableMigration(schema.notes,
                 columnTransformer: {schema.notes.title: schema.notes.title.trim()}));
           },
         ),
         beforeOpen: (details) async {
           await customStatement('PRAGMA foreign_keys = ON');
           if (kDebugMode) await validateDatabaseSchema();   // drift_dev/api/migrations_native.dart
         },
       );
   ```

   Steps use the **versioned** `schema` argument, never the current tables,
   so `from1To2` keeps compiling and meaning the same thing after version 7.

5. Run the generated tests (`SchemaVerifier`, PERSIST-008). They open a
   database at version N, migrate it to N+1 and compare it with the exported
   schema, and you can add data checks:

   ```dart
   test('v1 → v2 keeps notes and adds dueDate', () async {
     final schema = await verifier.schemaAt(1);
     final oldDb = v1.DatabaseAtV1(schema.newConnection());
     await oldDb.into(oldDb.notes).insert(v1.NotesCompanion.insert(title: 'a'));
     await oldDb.close();

     final db = AppDatabase(schema.newConnection());
     await verifier.migrateAndValidate(db, 2);
     expect((await db.select(db.notes).get()).single.title, 'a');
     await db.close();
   });
   ```

- `TableMigration` copies a table into a new definition (renames, type
  changes, new non-null columns with a `columnTransformer`).
- Turn foreign keys off during complex steps and check
  `PRAGMA foreign_key_check` afterwards, as drift's migration example does.
- Older projects use `drift_dev schema dump` / `schema steps` /
  `schema generate`; `make-migrations` wraps those commands.

## 2. sqflite

```dart
const _kVersion = 3;

Future<Database> open(String path) => openDatabase(
      path,
      version: _kVersion,
      onConfigure: (db) => db.execute('PRAGMA foreign_keys = ON'),
      onCreate: (db, version) async {
        final batch = db.batch();
        _createNotesV3(batch);           // the latest schema, in one place
        await batch.commit(noResult: true);
      },
      onUpgrade: (db, oldVersion, newVersion) async {
        final batch = db.batch();
        if (oldVersion < 2) batch.execute('ALTER TABLE notes ADD COLUMN tag TEXT');
        if (oldVersion < 3) _createAuthorsV3(batch);
        await batch.commit(noResult: true);
      },
      onDowngrade: onDatabaseDowngradeDelete,   // only for a rebuildable cache
    );
```

- `onCreate` builds the **latest** schema; `onUpgrade` walks each step with
  `if (oldVersion < N)`, never `==` (users skip versions).
- `onCreate` and `onUpgrade` already run inside a transaction; don't open
  another one with `db`.
- SQLite's `ALTER TABLE` is limited: to change a column, create the new
  table, copy, drop, rename (in one step).
- Test with `sqflite_common_ffi`: create the old schema by hand, insert rows,
  reopen with the new version, assert.

## 3. Hive

Hive has no schema versions; the adapters *are* the schema.

- **typeId**: unique across the app and never reused (PERSIST-004). Keep them
  in one file of constants.
- **@HiveField(n)**: unique within the type and never reused, even after the
  field is deleted (PERSIST-005). Adding a field with a new index is safe;
  give it a `defaultValue` so old records decode.
- **Changing a field's type** isn't supported in place: add a new field with a
  new index, read old-or-new in a getter, rewrite the records once.
- **Renaming a box** is a migration: open the old one, copy to the new one,
  `deleteBoxFromDisk` the old one, behind a stored "data version" flag.
- hive_ce's `@GenerateAdapters` keeps a `hive_adapters.g.yaml` with assigned
  ids and indexes; commit it.

## 4. shared_preferences and file renames

A renamed key reads as "missing", so users silently lose the setting
(`PERSIST-key-rename-without-migration`).

```dart
// run once at startup, before anything reads the settings
Future<void> migrateSettings(SharedPreferencesAsync prefs) async {
  final version = await prefs.getInt('settings.version') ?? 1;
  if (version < 2) {
    final old = await prefs.getBool('darkMode');
    if (old != null) await prefs.setString('settings.theme_mode', old ? 'dark' : 'light');
    await prefs.remove('darkMode');
  }
  await prefs.setInt('settings.version', 2);
}
```

The same applies to file paths and database file names: move or copy the old
file once, then record that the move happened.

## 5. Transactions and batches

- **DO** wrap multi-step writes that must succeed together in a transaction:
  "insert order + insert lines + mark cart empty", "save note + outbox row".
- **DO** batch bulk writes (PERSIST-007). Drift: `batch((b) =>
  b.insertAll(...))`; sqflite: `db.batch()` … `commit(noResult: true)`; Isar:
  one `writeTxn` around the loop; Hive: `putAll`.
- **DON'T** await network calls inside a database transaction; it holds the
  write lock for the whole request. Fetch first, then write in one
  transaction.
- **DON'T** nest a second transaction on the outer database object inside a
  sqflite transaction (`db` inside `db.transaction`): it deadlocks. Use the
  `txn` you were given. Drift nests transactions as savepoints for you.
- **CONSIDER** `insertOnConflictUpdate` / `ConflictAlgorithm.replace` for
  upserts instead of read-then-write, which races.

## 6. Destructive changes

`PERSIST-destructive-migration` (High): an `onUpgrade` that drops tables
holding user data, `onDowngrade: onDatabaseDowngradeDelete` on a non-cache
database, or `deleteFromDisk` on version mismatch. These are fine only for
data you can rebuild from the server. Say so in a comment, and make the
rebuild part of the same release.

## 7. Release checklist

- [ ] `schemaVersion` / `version` bumped exactly once for the release.
- [ ] One migration step per version, using versioned schemas (drift) or
      `oldVersion < N` (sqflite).
- [ ] Schemas exported and migration tests green (drift `make-migrations`,
      PERSIST-008).
- [ ] An upgrade test from the **oldest version still in the field**, with
      data.
- [ ] Hive ids and indexes only added, never reused.
- [ ] Renamed keys, boxes and files migrated once, behind a stored version.
- [ ] Nothing destructive unless the data is a rebuildable cache.
