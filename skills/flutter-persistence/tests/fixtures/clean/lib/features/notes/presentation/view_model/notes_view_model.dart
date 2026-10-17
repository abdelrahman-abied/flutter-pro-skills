import 'package:flutter/foundation.dart';

import '../../data/repositories/notes_repository.dart';

class NotesViewModel extends ChangeNotifier {
  NotesViewModel(this._repository);

  final NotesRepository _repository;
  final load = Command();

  Future<void> refresh() async {
    await load.execute('SELECT label');
    await _repository.titles();
  }
}

class Command {
  Future<void> execute(String label) async {}
}
