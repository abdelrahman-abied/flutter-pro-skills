import 'package:todo_api/todo_api.dart';

// Delegates to an API client from another package, so fetch() can fail.
// (A repository that only returns constants can't fail, and ERR-010 skips awaits on it.)
class TodoRepository {
  TodoRepository(this._api);
  final TodoApi _api;

  Future<List<String>> fetch() => _api.fetchTodos();
}
