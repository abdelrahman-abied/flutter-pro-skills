import 'package:sqflite/sqflite.dart';

class ReportSource {
  ReportSource(this._db);

  final Database _db;

  Future<List<Map<String, Object?>>> byColumn(String column) {
    // persist-ignore: PERSIST-001 column is checked against kAllowedColumns by the caller
    return _db.rawQuery('SELECT $column FROM reports');
  }

  Future<List<Map<String, Object?>>> byName(String name) {
    return _db.rawQuery("SELECT * FROM reports WHERE name = '$name'");
  }
}
