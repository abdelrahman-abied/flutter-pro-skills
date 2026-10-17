import '../../../../core/result.dart';
import '../entities/movie.dart';
import '../repositories/movie_repository.dart';

class GetTrending {
  const GetTrending(this._repo);

  final MovieRepository _repo;

  Future<Result<List<Movie>>> call() => _repo.trending();
}
