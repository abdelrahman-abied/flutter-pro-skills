import '../../../../core/database/app_database.dart';

abstract class NotesRepository {
  Future<List<String>> titles();
}

class NotesRepositoryLocal implements NotesRepository {
  NotesRepositoryLocal(this._db);

  final AppDatabase _db;
  final List<String> _recent = [];

  @override
  Future<List<String>> titles() async {
    for (final t in const ['a', 'b']) {
      _recent.insert(0, t);
    }
    final rows = await _db.select(_db.notes).get();
    return rows.map((r) => r.title).toList();
  }
}
