import 'package:dio/dio.dart';
import 'package:riverpod_annotation/riverpod_annotation.dart';

import '../models/movie_response.dart';

part 'movie_source.g.dart';

abstract interface class MovieSource {
  Future<List<MovieResponse>> getTrending();
}

class MovieRemoteSource implements MovieSource {
  final Dio _dio;
  const MovieRemoteSource(this._dio);

  @override
  Future<List<MovieResponse>> getTrending() async {
    final res = await _dio.get<List<Object?>>('/trending');
    return [for (final j in res.data!) MovieResponse.fromJson(j! as Map<String, dynamic>)];
  }
}

@riverpod
MovieSource movieSource(Ref ref) => MovieRemoteSource(Dio());
