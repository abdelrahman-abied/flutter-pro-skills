import '../entities/movie_entity.dart';
import '../../presentation/state/movie_state.dart';

abstract interface class MovieRepository {
  Future<List<MovieEntity>> fetchTrending();
  MovieState initialState();
}
