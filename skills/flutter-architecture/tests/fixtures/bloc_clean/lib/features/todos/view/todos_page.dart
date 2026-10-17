import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';

import '../../../repositories/todos_repository.dart';
import '../bloc/todos_bloc.dart';
import '../widgets/todo_tile.dart';

class TodosPage extends StatelessWidget {
  const TodosPage({super.key});

  @override
  Widget build(BuildContext context) => BlocProvider(
        create: (context) =>
            TodosBloc(repository: context.read<TodosRepository>())..add(const TodosSubscribed()),
        child: const TodosView(),
      );
}

class TodosView extends StatelessWidget {
  const TodosView({super.key});

  @override
  Widget build(BuildContext context) => BlocBuilder<TodosBloc, TodosState>(
        builder: (context, state) => ListView(
          children: [for (final t in state.todos) TodoTile(title: t)],
        ),
      );
}
