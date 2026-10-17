// lib/features/movie/data/sources/movie_source.dart
import 'package:riverpod_annotation/riverpod_annotation.dart';

import '../models/movie_response.dart';

part 'movie_source.g.dart';

abstract interface class MovieSource {
  Future<List<MovieResponse>> getTrending();
}

class MovieRemoteSource implements MovieSource {
  @override
  Future<List<MovieResponse>> getTrending() async {
    await Future<void>.delayed(const Duration(milliseconds: 500));
    return const [MovieResponse(id: '42', title: 'Interstellar')];
  }
}

@riverpod
MovieSource movieSource(Ref ref) => MovieRemoteSource();
