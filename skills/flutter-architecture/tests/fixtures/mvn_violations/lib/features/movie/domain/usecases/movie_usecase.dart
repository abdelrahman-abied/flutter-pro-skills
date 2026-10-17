import 'package:dio/dio.dart';
import 'package:riverpod_annotation/riverpod_annotation.dart';

import '../entities/movie_entity.dart';
import '../repositories/movie_repository.dart';
import '../../data/repositories/movie_repository_impl.dart';

part 'movie_usecase.g.dart';

class FetchTrendingMovies {
  const FetchTrendingMovies(this._repository);
  final MovieRepository _repository;

  Future<List<MovieEntity>> call() async {
    try {
      return await _repository.fetchTrending();
    } on DioException {
      return const [];
    }
  }
}

@riverpod
FetchTrendingMovies fetchTrendingMovies(Ref ref) =>
    FetchTrendingMovies(ref.watch(movieRepositoryProvider));
