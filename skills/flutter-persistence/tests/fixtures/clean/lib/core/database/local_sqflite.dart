import 'package:sqflite/sqflite.dart';

const kNotesTable = 'notes';
const _kVersion = 2;
final _placeholders = List.filled(3, '?').join(', ');

Future<Database> openNotesDatabase(String path) {
  return openDatabase(
    path,
    version: _kVersion,
    onCreate: (db, version) async {
      final batch = db.batch();
      batch.execute('CREATE TABLE $kNotesTable (id INTEGER PRIMARY KEY, title TEXT, tag TEXT)');
      await batch.commit();
    },
    onUpgrade: (db, oldVersion, newVersion) async {
      if (oldVersion < 2) {
        for (final column in const ['tag']) {
          await db.execute('ALTER TABLE $kNotesTable ADD COLUMN $column TEXT');
        }
      }
    },
  );
}

Future<Database> openPrefsDatabase(String path) => openDatabase(path, version: 1, onCreate: (db, v) async {});

Future<Database> openBundled(String path) =>
    openDatabase(path, version: 4, readOnly: true);

class NotesSqlSource {
  NotesSqlSource(this._db);

  final Database _db;

  Future<List<Map<String, Object?>>> byTitle(String title) =>
      _db.rawQuery('SELECT * FROM $kNotesTable WHERE title = ?', [title]);

  Future<List<Map<String, Object?>>> byTags(List<String> tags) =>
      _db.query(kNotesTable, where: 'tag IN ($_placeholders)', whereArgs: tags);

  Future<List<Map<String, Object?>>> page(int limit, int offset) =>
      _db.rawQuery('SELECT * FROM $kNotesTable LIMIT $limit OFFSET $offset');

  Future<List<Map<String, Object?>>> since(DateTime when) =>
      _db.rawQuery("SELECT * FROM notes WHERE updated > '${when.toIso8601String()}'");

  Future<List<Map<String, Object?>>> run(String sql, List<Object?> args) => _db.rawQuery(sql, args);

  Future<void> saveAll(List<Map<String, Object?>> rows) async {
    await _db.transaction((txn) async {
      for (final r in rows) {
        await txn.insert(kNotesTable, r);
      }
    });
    final batch = _db.batch();
    for (final r in rows) {
      batch.insert(kNotesTable, r);
    }
    await batch.commit(noResult: true);
  }
}
