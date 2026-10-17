import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';

import '../features/todos/view/todos_page.dart';
import '../repositories/todos_repository.dart';

class App extends StatelessWidget {
  const App({super.key, required this.todosRepository});
  final TodosRepository todosRepository;

  @override
  Widget build(BuildContext context) => RepositoryProvider.value(
        value: todosRepository,
        child: const MaterialApp(home: TodosPage()),
      );
}
