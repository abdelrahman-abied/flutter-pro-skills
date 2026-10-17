import 'package:sqflite/sqflite.dart';

const kGameStorageTable = 'game';
final _themeKeys = ['opening', 'endgame'];
final _themeKeysPlaceholders = List.filled(_themeKeys.length, '?').join(', ');

class GameStorage {
  const GameStorage(this._db);

  final Database _db;

  Future<int> count(String userId) async {
    final result = await _db.rawQuery('SELECT COUNT(*) as cnt FROM $kGameStorageTable WHERE userId = ?', [userId]);
    return Sqflite.firstIntValue(result) ?? 0;
  }

  Future<List<Map<String, Object?>>> byThemes(String userId) {
    return _db.query(
      kGameStorageTable,
      where: 'userId = ? AND angle IN ($_themeKeysPlaceholders)',
      whereArgs: [userId, ..._themeKeys],
    );
  }

  Future<List<Map<String, Object?>>> search(String term) {
    return _db.rawQuery("SELECT * FROM $kGameStorageTable WHERE white LIKE '%$term%'");
  }
}
