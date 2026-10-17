// lib/features/movie/domain/usecases/movie_usecase.dart
import 'package:riverpod_annotation/riverpod_annotation.dart';

import '../entities/movie_entity.dart';
import '../repositories/movie_repository.dart';
// DI seam: the use-case PROVIDER may reference the data provider; the class stays pure.
import '../../data/repositories/movie_repository_impl.dart';

part 'movie_usecase.g.dart';

class FetchTrendingMovies {
  final MovieRepository _repository;
  const FetchTrendingMovies(this._repository);

  Future<List<MovieEntity>> call() => _repository.fetchTrending();
}

@riverpod
FetchTrendingMovies fetchTrendingMovies(Ref ref) =>
    FetchTrendingMovies(ref.watch(movieRepositoryProvider));
