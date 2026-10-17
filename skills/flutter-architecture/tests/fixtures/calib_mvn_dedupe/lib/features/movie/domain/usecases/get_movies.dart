import '../repositories/movie_repository.dart';

class GetMovies {
  GetMovies(this._r);
  final MovieRepository _r;
  Future<List<String>> call() => _r.all();
}
