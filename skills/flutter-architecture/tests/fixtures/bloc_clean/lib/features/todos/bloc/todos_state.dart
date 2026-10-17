part of 'todos_bloc.dart';

final class TodosState extends Equatable {
  const TodosState({this.todos = const []});
  final List<String> todos;

  TodosState copyWith({List<String>? todos}) => TodosState(todos: todos ?? this.todos);

  @override
  List<Object> get props => [todos];
}
