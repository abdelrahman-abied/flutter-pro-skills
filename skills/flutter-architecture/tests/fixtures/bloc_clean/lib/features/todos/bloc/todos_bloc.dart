import 'package:bloc/bloc.dart';
import 'package:equatable/equatable.dart';

import '../../../repositories/todos_repository.dart';

part 'todos_event.dart';
part 'todos_state.dart';

class TodosBloc extends Bloc<TodosEvent, TodosState> {
  TodosBloc({required TodosRepository repository})
      : _repository = repository,
        super(const TodosState()) {
    on<TodosSubscribed>((event, emit) => emit.forEach<List<String>>(
          _repository.watchTodos(),
          onData: (todos) => state.copyWith(todos: todos),
        ));
    on<TodoAdded>((event, emit) => _repository.add(event.title));
  }

  final TodosRepository _repository;
}
