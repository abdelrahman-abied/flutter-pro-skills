import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../notifier/movie_notifier.dart';
import '../state/movie_state.dart';

class MovieView extends ConsumerWidget {
  const MovieView({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    ref.listen(movieNotifierProvider, (previous, next) {
      if (next is MovieError) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(next.message)));
      }
    });
    final state = ref.watch(movieNotifierProvider);
    return Scaffold(
      body: switch (state) {
        MovieInitial() || MovieLoading() => const Center(child: CircularProgressIndicator()),
        MovieError(:final message) => Center(child: Text(message)),
        MovieSuccess(:final movies) => ListView(children: [for (final m in movies) Text(m.title)]),
      },
    );
  }
}
