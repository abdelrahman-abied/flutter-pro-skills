import 'package:drift/drift.dart';

import '../../../../core/database/app_database.dart';
import '../../domain/entities/note.dart';
import '../../domain/repositories/notes_repository.dart';

class NotesRepositoryImpl implements NotesRepository {
  NotesRepositoryImpl(this._executor);

  final QueryExecutor _executor;

  @override
  Future<List<Note>> loadNotes() async {
    final db = AppDatabase(_executor);
    final rows = await db.select(db.notes).get();
    await db.close();
    return rows.map((r) => Note(r.id, r.title)).toList();
  }

  @override
  Future<void> importNotes(List<Note> notes, AppDatabase db) async {
    for (final n in notes) {
      await db.into(db.notes).insert(NotesCompanion.insert(title: n.title));
    }
  }
}
