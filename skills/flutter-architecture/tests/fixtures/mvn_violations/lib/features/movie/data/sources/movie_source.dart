import 'package:dio/dio.dart';
import 'package:riverpod_annotation/riverpod_annotation.dart';

import '../models/movie_response.dart';

part 'movie_source.g.dart';

abstract interface class MovieSource {
  Future<List<MovieResponse>> getTrending();
}

class MovieRemoteSource implements MovieSource {
  MovieRemoteSource(this._dio);
  final Dio _dio;

  @override
  Future<List<MovieResponse>> getTrending() async {
    final res = await _dio.get<List<dynamic>>('/trending');
    return [for (final j in res.data ?? const []) MovieResponse.fromJson(j as Map<String, dynamic>)];
  }
}

@riverpod
MovieSource movieSource(Ref ref) => MovieRemoteSource(Dio());
