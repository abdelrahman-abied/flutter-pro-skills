import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

final todosProvider = Provider<List<String>>((ref) => const []);

// FP 5 (severity): a ListView mixing fixed header widgets with one data loop is low, not medium.
class Home extends ConsumerWidget {
  const Home({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final todos = ref.watch(todosProvider);
    return ListView(
      children: [
        const Text('todos'),
        const TextField(),
        if (todos.isNotEmpty) const Divider(height: 0),
        for (var i = 0; i < todos.length; i++) ...[
          if (i > 0) const Divider(height: 0),
          Text(todos[i]),
        ],
      ],
    );
  }
}

// TP 6: a ListView whose children are only the data list stays medium.
class AllTodos extends ConsumerWidget {
  const AllTodos({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final todos = ref.watch(todosProvider);
    return ListView(children: [for (final t in todos) Text(t)]);
  }
}
