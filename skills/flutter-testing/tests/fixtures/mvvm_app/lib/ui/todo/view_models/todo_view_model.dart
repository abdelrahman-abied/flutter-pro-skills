import 'package:flutter/foundation.dart';

import '../../../data/repositories/todo_repository.dart';
import '../../../domain/models/todo.dart';

class TodoViewModel extends ChangeNotifier {
  TodoViewModel({required TodoRepository todoRepository}) : _repository = todoRepository;

  final TodoRepository _repository;
  List<Todo> todos = const [];
  Object? error;

  Future<void> load() async {
    try {
      todos = await _repository.fetchTodos();
      error = null;
    } catch (e) {
      error = e;
    }
    notifyListeners();
  }
}
