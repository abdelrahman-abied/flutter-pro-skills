import 'package:flutter_bloc/flutter_bloc.dart';

import '../data/todo_repository.dart';

enum TodoStatus { initial, loading, success, failure }

final class TodoListState {
  const TodoListState({this.status = TodoStatus.initial, this.todos = const []});
  final TodoStatus status;
  final List<String> todos;

  TodoListState copyWith({TodoStatus? status, List<String>? todos}) =>
      TodoListState(status: status ?? this.status, todos: todos ?? this.todos);
}

class TodoCubit extends Cubit<TodoListState> {
  TodoCubit(this._repo) : super(const TodoListState());

  final TodoRepository _repo;

  Future<void> load() async {
    emit(state.copyWith(status: TodoStatus.loading));
    final todos = await _repo.fetch();
    emit(state.copyWith(status: TodoStatus.success, todos: todos));
  }

  Future<void> reload() async {
    emit(state.copyWith(status: TodoStatus.loading));
    try {
      final todos = await _repo.fetch();
      emit(state.copyWith(status: TodoStatus.success, todos: todos));
    } on Exception {
      emit(state.copyWith(status: TodoStatus.failure));
    }
  }
}
