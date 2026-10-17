// lib/features/movie/domain/repositories/movie_repository.dart
import '../entities/movie_entity.dart';

abstract interface class MovieRepository {
  Future<List<MovieEntity>> fetchTrending();
}
