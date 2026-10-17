import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'package:mvn_conventions/features/movie/presentation/notifiers/movie_notifier.dart';
import 'package:mvn_conventions/features/movie/presentation/state/movie_state.dart';
import 'package:mvn_conventions/features/movie/presentation/widgets/movie_list.dart';

class MoviePage extends ConsumerWidget {
  const MoviePage({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final state = ref.watch(movieProvider);
    return Scaffold(
      body: switch (state) {
        MovieInitial() => Center(
            child: TextButton(
              onPressed: ref.read(movieProvider.notifier).load,
              child: const Text('Load'),
            ),
          ),
        MovieSuccess(movies: final m) => MovieList(movies: m),
      },
    );
  }
}
