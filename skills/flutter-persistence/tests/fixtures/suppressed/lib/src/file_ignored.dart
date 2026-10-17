// persist-ignore-file: PERSIST-007 one-off import tool, runs once on a desktop build
import 'package:sqflite/sqflite.dart';

Future<void> importRows(Database db, List<Map<String, Object?>> rows) async {
  for (final r in rows) {
    await db.insert('reports', r);
  }
}

Future<void> importMore(Database db, List<Map<String, Object?>> rows) async {
  for (final r in rows) {
    await db.insert('archive', r);
  }
}
