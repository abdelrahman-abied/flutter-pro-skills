import 'package:riverpod_annotation/riverpod_annotation.dart';

import '../../domain/entities/movie_entity.dart';
import '../../domain/repositories/movie_repository.dart';
import '../../presentation/notifier/movie_notifier.dart';
import '../../presentation/state/movie_state.dart';
import '../sources/movie_source.dart';

part 'movie_repository_impl.g.dart';

class MovieRepositoryImpl implements MovieRepository {
  MovieRepositoryImpl(this._source);
  final MovieSource _source;

  @override
  Future<List<MovieEntity>> fetchTrending() async =>
      [for (final r in await _source.getTrending()) MovieEntity.fromResponse(r)];

  /// ARCH-107: leaks the transport shape.
  Future<Map<String, dynamic>> rawTrending() async => {'count': (await _source.getTrending()).length};

  @override
  MovieState initialState() => MovieState(page: kFirstPage);
}

@riverpod
MovieRepository movieRepository(Ref ref) => MovieRepositoryImpl(ref.watch(movieSourceProvider));
