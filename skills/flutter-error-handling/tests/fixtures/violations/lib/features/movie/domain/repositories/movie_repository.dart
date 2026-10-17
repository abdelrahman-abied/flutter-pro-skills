import '../../../../core/result.dart';
import '../entities/movie.dart';

abstract interface class MovieRepository {
  Future<List<Movie>> trending();
  Future<Movie?> byTitle(String title);
  Future<Result<String>> token();
}
