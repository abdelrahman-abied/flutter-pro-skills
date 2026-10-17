import 'package:riverpod_annotation/riverpod_annotation.dart';

import 'package:mvn_conventions/features/movie/data/repositories/movie_repository_impl.dart';
import 'package:mvn_conventions/features/movie/domain/entities/movie_entity.dart';
import 'package:mvn_conventions/features/movie/domain/repositories/movie_repository.dart';

part 'movie_usecase.g.dart';

class FetchTrendingMovies {
  final MovieRepository _repository;
  const FetchTrendingMovies(this._repository);

  Future<List<MovieEntity>> call() => _repository.fetchTrending();
}

@riverpod
FetchTrendingMovies fetchTrendingMovies(Ref ref) =>
    FetchTrendingMovies(ref.watch(movieRepositoryProvider));
