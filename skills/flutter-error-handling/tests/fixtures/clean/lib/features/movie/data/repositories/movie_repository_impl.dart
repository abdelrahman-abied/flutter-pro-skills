import 'package:dio/dio.dart';

import '../../../../core/failure.dart';
import '../../../../core/result.dart';
import '../../domain/entities/movie.dart';
import '../../domain/repositories/movie_repository.dart';
import '../sources/movie_api.dart';

class MovieRepositoryImpl implements MovieRepository {
  MovieRepositoryImpl(this._api);

  final MovieApi _api;

  @override
  Future<Result<List<Movie>>> trending() async {
    try {
      final rows = await _api.trending();
      return Result.ok([for (final r in rows) Movie(r['title'] as String)]);
    } on DioException catch (e) {
      return Result.error(_mapDio(e));
    } on FormatException {
      return const Result.error(ParseFailure());
    }
  }

  Failure _mapDio(DioException e) => switch (e.type) {
        DioExceptionType.connectionError || DioExceptionType.connectionTimeout => const NetworkFailure(),
        _ => ServerFailure(e.response?.statusCode),
      };
}
