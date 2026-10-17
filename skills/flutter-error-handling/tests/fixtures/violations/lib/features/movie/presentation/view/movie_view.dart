import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../notifier/movie_notifier.dart';
import '../state/movie_state.dart';

class MovieView extends ConsumerWidget {
  const MovieView({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final state = ref.watch(movieNotifierProvider);
    return Scaffold(
      floatingActionButton: FloatingActionButton(
        onPressed: () async {
          try {
            await ref.read(movieNotifierProvider.notifier).refresh();
          } catch (e) {
            ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(e.toString())));
          }
          ref.read(movieNotifierProvider.notifier).load().catchError((Object _) {});
        },
        child: const Icon(Icons.refresh),
      ),
      body: switch (state) {
        MovieInitial() || MovieLoading() => const Center(child: CircularProgressIndicator()),
        MovieError(:final message) => Center(child: Text(message)),
        MovieSuccess(:final movies) => ListView(children: [for (final m in movies) Text(m.title)]),
      },
    );
  }
}
