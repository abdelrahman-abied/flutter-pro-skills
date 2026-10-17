import 'package:sqflite/sqflite.dart';

const kLegacyVersion = 3;

Future<Database> openLegacyDatabase(String path) {
  return openDatabase(
    path,
    version: kLegacyVersion,
    onCreate: (db, version) async {
      await db.execute('CREATE TABLE notes (id INTEGER PRIMARY KEY, title TEXT, body TEXT)');
    },
  );
}
