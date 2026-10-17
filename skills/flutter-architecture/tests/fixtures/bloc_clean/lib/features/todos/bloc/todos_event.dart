part of 'todos_bloc.dart';

sealed class TodosEvent extends Equatable {
  const TodosEvent();
  @override
  List<Object> get props => [];
}

final class TodosSubscribed extends TodosEvent {
  const TodosSubscribed();
}

final class TodoAdded extends TodosEvent {
  const TodoAdded(this.title);
  final String title;
  @override
  List<Object> get props => [title];
}
