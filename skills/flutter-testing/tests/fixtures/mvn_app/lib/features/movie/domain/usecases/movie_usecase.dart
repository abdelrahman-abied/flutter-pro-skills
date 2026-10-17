import 'package:riverpod_annotation/riverpod_annotation.dart';

import '../../data/repositories/movie_repository_impl.dart';
import '../entities/movie_entity.dart';
import '../repositories/movie_repository.dart';

part 'movie_usecase.g.dart';

class FetchTrendingMovies {
  final MovieRepository _repository;
  const FetchTrendingMovies(this._repository);

  Future<List<MovieEntity>> call() async {
    final movies = await _repository.fetchTrending();
    return movies.where((m) => m.title.isNotEmpty).toList();
  }
}

@riverpod
FetchTrendingMovies fetchTrendingMovies(Ref ref) =>
    FetchTrendingMovies(ref.watch(movieRepositoryProvider));
