import 'dart:io';

import '../entities/movie.dart';
import '../repositories/movie_repository.dart';

class GetTrending {
  const GetTrending(this._repo);

  final MovieRepository _repo;

  Future<List<Movie>> call() async {
    try {
      return await _repo.trending();
    } on SocketException catch (e) {
      throw HttpException('offline: ${e.message}');
    }
  }
}
