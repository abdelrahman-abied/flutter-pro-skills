import '../../domain/models/todo.dart';
import '../services/api_client.dart';

abstract class TodoRepository {
  Future<List<Todo>> fetchTodos();
}

class TodoRepositoryRemote implements TodoRepository {
  final ApiClient _api;
  TodoRepositoryRemote(this._api);

  @override
  Future<List<Todo>> fetchTodos() async {
    final json = await _api.getTodos();
    return [
      for (final j in json)
        if (j['title'] != null) Todo(id: j['id']! as int, title: j['title']! as String),
    ];
  }
}
