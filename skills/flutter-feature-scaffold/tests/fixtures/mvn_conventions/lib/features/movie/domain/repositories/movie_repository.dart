import 'package:mvn_conventions/features/movie/domain/entities/movie_entity.dart';

abstract interface class MovieRepository {
  Future<List<MovieEntity>> fetchTrending();
}
