import '../../../../core/result.dart';
import '../entities/movie.dart';

abstract interface class MovieRepository {
  Future<Result<List<Movie>>> trending();
}
