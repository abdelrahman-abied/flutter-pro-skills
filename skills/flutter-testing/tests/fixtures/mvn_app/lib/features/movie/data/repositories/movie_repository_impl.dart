import 'package:riverpod_annotation/riverpod_annotation.dart';

import '../../domain/entities/movie_entity.dart';
import '../../domain/repositories/movie_repository.dart';
import '../sources/movie_source.dart';

part 'movie_repository_impl.g.dart';

class MovieRepositoryImpl implements MovieRepository {
  final MovieSource _source;
  const MovieRepositoryImpl(this._source);

  @override
  Future<List<MovieEntity>> fetchTrending() async {
    final responses = await _source.getTrending();
    return responses.map((r) => r.toEntity()).toList();
  }
}

@riverpod
MovieRepository movieRepository(Ref ref) =>
    MovieRepositoryImpl(ref.watch(movieSourceProvider));
