import 'package:riverpod_annotation/riverpod_annotation.dart';

import '../../../../core/failure.dart';
import '../../../../core/result.dart';
import '../../domain/usecases/get_trending.dart';
import '../state/movie_state.dart';

part 'movie_notifier.g.dart';

@riverpod
GetTrending getTrending(Ref ref) => throw UnimplementedError('overridden in ProviderScope');

@riverpod
class MovieNotifier extends _$MovieNotifier {
  @override
  MovieState build() => const MovieInitial();

  Future<void> load() async {
    state = const MovieLoading();
    switch (await ref.read(getTrendingProvider)()) {
      case Ok(:final value):
        state = MovieSuccess(value);
      case Error(:final error):
        state = MovieError(error is Failure ? error.userMessage : 'Something went wrong.');
    }
  }
}
