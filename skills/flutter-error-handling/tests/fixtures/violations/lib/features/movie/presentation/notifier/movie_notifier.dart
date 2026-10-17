import 'package:riverpod_annotation/riverpod_annotation.dart';

import '../../domain/usecases/get_trending.dart';
import '../state/movie_state.dart';

part 'movie_notifier.g.dart';

@riverpod
GetTrending getTrending(Ref ref) => throw UnimplementedError();

@riverpod
class MovieNotifier extends _$MovieNotifier {
  @override
  MovieState build() => const MovieInitial();

  Future<void> load() async {
    state = const MovieLoading();
    final movies = await ref.read(getTrendingProvider)();
    state = MovieSuccess(movies);
  }

  Future<void> refresh() async {
    try {
      final movies = await ref.read(getTrendingProvider)();
      state = MovieSuccess(movies);
    } catch (e) {
      state = MovieError(e.toString());
    }
  }
}
