import 'package:drift/drift.dart';

import 'database.drift.dart';

const _legacyDateColumns = <String, List<String>>{
  'user_entity': ['profile_changed_at'],
  'local_asset_entity': ['created_at', 'updated_at'],
};

@DriftDatabase(tables: [], daos: [])
class Drift extends $Drift {
  Drift(super.executor);

  Drift.sqlite(Object db, Object pool) : super(openPool(db, pool));

  @override
  int get schemaVersion => 35;

  @override
  MigrationStrategy get migration => MigrationStrategy(
        onUpgrade: (m, from, to) async {
          await customStatement('PRAGMA foreign_keys = OFF');
          await customStatement('PRAGMA user_version = $to');
        },
      );
}

@DriftDatabase(tables: [])
class DriftLogger extends $DriftLogger {
  DriftLogger.sqlite(Object db) : super(openPool(db, db));

  @override
  int get schemaVersion => 2;
}

Future<void> healDateTimes(GeneratedDatabase db) async {
  const floor = '0001-01-01T00:00:00.000Z';
  for (final MapEntry(key: table, value: columns) in _legacyDateColumns.entries) {
    String low(String c) => "substr($c, 1, 1) = '-'";
    final assignments = columns.map((c) => "$c = CASE WHEN ${low(c)} THEN '$floor' ELSE $c END");
    await db.customStatement('UPDATE $table SET ${assignments.join(', ')}');
  }
}

Future<void> healTables(GeneratedDatabase db, Map<String, List<String>> tables) async {
  for (final MapEntry(key: table, value: columns) in tables.entries) {
    await db.customStatement('UPDATE $table SET ${columns.first} = NULL');
  }
}

QueryExecutor openPool(Object db, Object pool) => throw UnimplementedError();
