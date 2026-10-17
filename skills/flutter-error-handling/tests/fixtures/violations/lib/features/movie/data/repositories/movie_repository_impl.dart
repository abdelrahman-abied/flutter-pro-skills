import 'package:flutter/foundation.dart';

import '../../../../core/result.dart';
import '../../domain/entities/movie.dart';
import '../../domain/repositories/movie_repository.dart';
import '../sources/movie_api.dart';

class MovieRepositoryImpl implements MovieRepository {
  MovieRepositoryImpl(this._api);

  final MovieApi _api;

  @override
  Future<List<Movie>> trending() async {
    final rows = await _api.trending();
    return [for (final r in rows) Movie(r['title'] as String)];
  }

  @override
  Future<Movie?> byTitle(String title) async {
    try {
      final rows = await _api.trending();
      return rows.map((r) => Movie(r['title'] as String)).firstWhere((m) => m.title == title);
    } catch (e) {
      debugPrint('byTitle failed: $e');
      return null;
    }
  }

  @override
  Future<Result<String>> token() async {
    final t = await _api.token();
    if (t.isEmpty) throw const FormatException('empty token');
    return Result.ok(t);
  }
}
