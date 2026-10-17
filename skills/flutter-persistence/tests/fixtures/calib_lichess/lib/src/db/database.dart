import 'package:sqflite/sqflite.dart';

const puzzleTTL = Duration(days: 60);

Future<Database> openLocalDb(DatabaseFactory factory, String path) {
  return factory.openDatabase(
    path,
    options: OpenDatabaseOptions(
      version: 8,
      onOpen: (db) async {
        await db.transaction((txn) async {
          await _purgeExpired(txn, 'puzzle', puzzleTTL);
        });
      },
      onCreate: (db, version) async {},
      onUpgrade: (db, oldVersion, newVersion) async {},
    ),
  );
}

Future<Database> openOpenings(DatabaseFactory f, String path) =>
    f.openDatabase(path, options: OpenDatabaseOptions(readOnly: true));

Future<void> _purgeExpired(DatabaseExecutor db, String table, Duration ttl) async {
  final date = DateTime.now().subtract(ttl);
  if (!await _tableExists(db, table)) {
    return;
  }
  await db.delete(table, where: 'lastModified < ?', whereArgs: [date.toIso8601String()]);
}

Future<bool> _tableExists(DatabaseExecutor db, String table) async {
  final tableExists = await db.rawQuery(
    "SELECT name FROM sqlite_master WHERE type='table' AND name='$table'",
  );
  return tableExists.isNotEmpty;
}
