import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../notifier/movie_notifier.dart';
import '../state/movie_state.dart';
import '../widget/movie_list.dart';

class MovieView extends ConsumerWidget {
  const MovieView({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final state = ref.watch(movieNotifierProvider);
    return Scaffold(
      body: switch (state) {
        MovieLoading() => const Center(child: CircularProgressIndicator()),
        MovieError(:final message) => Center(child: Text(message)),
        MovieSuccess(:final movies) => MovieList(movies: movies),
      },
    );
  }
}
