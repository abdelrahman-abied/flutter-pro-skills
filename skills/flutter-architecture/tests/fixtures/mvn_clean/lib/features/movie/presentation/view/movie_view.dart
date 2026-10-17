// lib/features/movie/presentation/view/movie_view.dart
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../notifier/movie_notifier.dart';
import '../state/movie_state.dart';
import '../widget/movie_list.dart';

class MovieView extends ConsumerWidget {
  const MovieView({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    // One-time side effects, outside the paint pipeline.
    ref.listen<MovieState>(movieNotifierProvider, (previous, current) {
      if (current is MovieError) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(current.message)),
        );
      }
    });

    final state = ref.watch(movieNotifierProvider);

    return Scaffold(
      appBar: AppBar(title: const Text('Clean Architecture + MVN')),
      body: switch (state) {
        MovieInitial() => Center(
            child: ElevatedButton(
              onPressed: ref.read(movieNotifierProvider.notifier).loadTrending,
              child: const Text('Fetch Trends'),
            ),
          ),
        MovieLoading() => const Center(child: CircularProgressIndicator()),
        MovieError(message: final m) => Center(child: Text(m)),
        MovieSuccess(movies: final list) => MovieList(movies: list),
      },
    );
  }
}
