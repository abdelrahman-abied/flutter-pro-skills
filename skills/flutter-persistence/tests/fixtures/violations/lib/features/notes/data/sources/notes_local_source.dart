import 'package:sqflite/sqflite.dart';

import '../models/note_model.dart';

const kNotesTable = 'notes';

class NotesLocalSource {
  NotesLocalSource(this._db);

  final Database _db;
  String sortColumn = 'title';

  Future<List<Map<String, Object?>>> search(String query) {
    return _db.rawQuery("SELECT * FROM $kNotesTable WHERE title LIKE '%$query%'");
  }

  Future<List<Map<String, Object?>>> byAuthor(String author) {
    return _db.rawQuery('SELECT * FROM notes WHERE author = ' + author);
  }

  Future<List<Map<String, Object?>>> sorted() {
    return _db.rawQuery('SELECT * FROM notes ORDER BY $sortColumn');
  }

  Future<List<Map<String, Object?>>> byTag(String tag) {
    return _db.query(kNotesTable, where: "tag = '$tag'");
  }

  Future<void> saveAll(List<NoteModel> notes) async {
    for (final note in notes) {
      await _db.insert(kNotesTable, note.toMap());
    }
  }
}
