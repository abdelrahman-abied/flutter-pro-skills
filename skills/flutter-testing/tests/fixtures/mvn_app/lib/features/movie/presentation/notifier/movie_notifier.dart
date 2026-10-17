import 'package:riverpod_annotation/riverpod_annotation.dart';

import '../../domain/usecases/movie_usecase.dart';
import '../state/movie_state.dart';

part 'movie_notifier.g.dart';

@riverpod
class MovieNotifier extends _$MovieNotifier {
  @override
  MovieState build() => const MovieLoading();

  Future<void> load() async {
    state = const MovieLoading();
    try {
      final movies = await ref.read(fetchTrendingMoviesProvider)();
      state = MovieSuccess(movies);
    } catch (e) {
      state = MovieError('$e');
    }
  }
}
