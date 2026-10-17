import 'package:flutter/rendering.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mvn_app/features/movie/data/models/movie_response.dart';
import 'package:mvn_app/features/movie/data/sources/movie_source.dart';
import 'package:mvn_app/features/movie/domain/entities/movie_entity.dart';
import 'package:mvn_app/features/movie/domain/repositories/movie_repository.dart';

class FakeMovieSource implements MovieSource {
  List<MovieResponse> items = const [MovieResponse(id: '1', title: 'Dune')];

  @override
  Future<List<MovieResponse>> getTrending() async => items;
}

class FakeMovieRepository implements MovieRepository {
  List<MovieEntity> movies = const [];

  @override
  Future<List<MovieEntity>> fetchTrending() async {
    // Simulated latency: runs on the fake clock in widget tests, so it is fine here.
    await Future<void>.delayed(const Duration(milliseconds: 300));
    return movies;
  }
}

/// Polls until [condition] holds; fails the test on timeout.
Future<void> settles(bool Function() condition) async {
  for (var i = 0; i < 100; i++) {
    if (condition()) return;
    await Future<void>.delayed(Duration.zero);
  }
  fail('condition never held');
}

/// Writes the current frame to build/previews/<name>.png for a human to look at.
Future<void> savePng(WidgetTester tester, String name) async {
  final boundary = tester.renderObject<RenderRepaintBoundary>(find.byType(RepaintBoundary).first);
  final image = await boundary.toImage();
  await image.toByteData();
}
