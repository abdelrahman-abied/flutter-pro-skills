import '../entities/note.dart';
import '../repositories/notes_repository.dart';

class LoadNotesUseCase {
  const LoadNotesUseCase(this._repository);

  final NotesRepository _repository;

  Future<List<Note>> call() => _repository.loadNotes();
}
