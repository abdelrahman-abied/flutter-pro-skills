import 'package:drift/drift.dart';

import 'app_database.steps.dart';

part 'app_database.g.dart';

class Notes extends Table {
  IntColumn get id => integer().autoIncrement()();
  TextColumn get title => text()();
}

// Encrypted with SQLCipher (sqlcipher_flutter_libs), so a sensitive table name is fine here.
class PaymentMethods extends Table {
  IntColumn get id => integer().autoIncrement()();
  TextColumn get last4 => text()();
}

@DriftDatabase(tables: [Notes, PaymentMethods])
class AppDatabase extends _$AppDatabase {
  AppDatabase(super.e);

  static final AppDatabase instance = AppDatabase(_open());

  @override
  int get schemaVersion => 2;

  @override
  MigrationStrategy get migration => MigrationStrategy(
        onUpgrade: stepByStep(
          from1To2: (m, schema) async {
            await m.addColumn(schema.notes, schema.notes.title);
          },
        ),
        beforeOpen: (details) async {
          await customStatement('PRAGMA foreign_keys = ON');
          await customStatement('PRAGMA user_version = $schemaVersion');
        },
      );

  Future<int> countByTitle(String title) async {
    final row = await customSelect(
      'SELECT COUNT(*) AS c FROM notes WHERE title = ?',
      variables: [Variable.withString(title)],
    ).getSingle();
    return row.read<int>('c');
  }

  Future<void> importTitles(List<String> titles) {
    return transaction(() async {
      for (final t in titles) {
        await into(notes).insert(NotesCompanion.insert(title: t));
      }
    });
  }

  Future<void> importBatch(List<String> titles) async {
    await batch((b) {
      for (final t in titles) {
        b.insert(notes, NotesCompanion.insert(title: t));
      }
    });
  }
}

const _key = 'from-secure-storage-at-runtime';

QueryExecutor _open() {
  final escapedKey = _key.replaceAll("'", "''");
  return LazyDatabase(() async {
    final db = openRaw();
    db.execute("PRAGMA key = '$escapedKey'");
    return db;
  });
}

dynamic openRaw() => throw UnimplementedError();
