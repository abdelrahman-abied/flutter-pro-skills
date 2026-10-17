import 'package:riverpod_annotation/riverpod_annotation.dart';

import 'package:mvn_conventions/features/movie/data/models/movie_response.dart';

part 'movie_source.g.dart';

abstract interface class MovieSource {
  Future<List<MovieResponse>> getTrending();
}

class MovieRemoteSource implements MovieSource {
  @override
  Future<List<MovieResponse>> getTrending() async => const [];
}

@riverpod
MovieSource movieSource(Ref ref) => MovieRemoteSource();
