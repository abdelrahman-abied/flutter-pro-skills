import 'dart:async';

import 'package:shared_preferences/shared_preferences.dart';

import 'todos_repository.dart';

class LocalTodosRepository implements TodosRepository {
  LocalTodosRepository(this._prefs);
  final SharedPreferences _prefs;
  final _controller = StreamController<List<String>>.broadcast();

  @override
  Stream<List<String>> watchTodos() => _controller.stream;

  @override
  Future<void> add(String title) async {
    final next = [...?_prefs.getStringList('todos'), title];
    await _prefs.setStringList('todos', next);
    _controller.add(next);
  }
}
