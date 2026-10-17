import '../entities/note.dart';

abstract interface class NotesRepository {
  Future<List<Note>> loadNotes();
}
