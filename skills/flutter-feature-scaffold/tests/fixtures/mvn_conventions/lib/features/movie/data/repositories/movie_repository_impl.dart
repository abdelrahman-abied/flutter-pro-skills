import 'package:riverpod_annotation/riverpod_annotation.dart';

import 'package:mvn_conventions/features/movie/data/sources/movie_source.dart';
import 'package:mvn_conventions/features/movie/domain/entities/movie_entity.dart';
import 'package:mvn_conventions/features/movie/domain/repositories/movie_repository.dart';

part 'movie_repository_impl.g.dart';

class MovieRepositoryImpl implements MovieRepository {
  final MovieSource _source;
  const MovieRepositoryImpl(this._source);

  @override
  Future<List<MovieEntity>> fetchTrending() async =>
      [for (final r in await _source.getTrending()) r.toEntity()];
}

@riverpod
MovieRepository movieRepository(Ref ref) => MovieRepositoryImpl(ref.watch(movieSourceProvider));
