import '../entities/movie_entity.dart';

abstract interface class MovieRepository {
  Future<List<MovieEntity>> fetchTrending();
}
