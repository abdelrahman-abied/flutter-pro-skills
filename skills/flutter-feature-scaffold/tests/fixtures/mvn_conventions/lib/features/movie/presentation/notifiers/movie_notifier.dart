import 'package:riverpod_annotation/riverpod_annotation.dart';

import 'package:mvn_conventions/features/movie/domain/usecases/movie_usecase.dart';
import 'package:mvn_conventions/features/movie/presentation/state/movie_state.dart';

part 'movie_notifier.g.dart';

@riverpod
class MovieNotifier extends _$MovieNotifier {
  @override
  MovieState build() => const MovieInitial();

  Future<void> load() async {
    state = MovieSuccess(await ref.read(fetchTrendingMoviesProvider)());
  }
}
