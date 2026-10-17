import 'package:flutter_bloc/flutter_bloc.dart';

import '../data/todo_repository.dart';

sealed class TodoEvent {}

final class TodosRequested extends TodoEvent {}

sealed class TodoState {
  const TodoState();
}

final class TodoInitial extends TodoState {
  const TodoInitial();
}

final class TodoLoading extends TodoState {
  const TodoLoading();
}

final class TodoLoaded extends TodoState {
  const TodoLoaded(this.todos);
  final List<String> todos;
}

final class TodoFailure extends TodoState {
  const TodoFailure(this.message);
  final String message;
}

class TodoBloc extends Bloc<TodoEvent, TodoState> {
  TodoBloc(this._repo) : super(const TodoInitial()) {
    on<TodosRequested>((event, emit) async {
      emit(const TodoLoading());
      final todos = await _repo.fetch();
      emit(TodoLoaded(todos));
    });
  }

  final TodoRepository _repo;
}
