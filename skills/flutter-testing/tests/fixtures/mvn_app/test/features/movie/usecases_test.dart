import 'package:flutter_test/flutter_test.dart';
import 'package:mvn_app/features/movie/domain/entities/movie_entity.dart';
import 'package:mvn_app/features/movie/domain/usecases/movie_usecase.dart';

import '../../helpers/fakes.dart';

void main() {
  test('drops movies without a title', () async {
    final repository = FakeMovieRepository()
      ..movies = const [MovieEntity(id: '1', title: ''), MovieEntity(id: '2', title: 'Heat')];
    final movies = await FetchTrendingMovies(repository)();
    expect(movies.map((m) => m.id), ['2']);
  });
}
