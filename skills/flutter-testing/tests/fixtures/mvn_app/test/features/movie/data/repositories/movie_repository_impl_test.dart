import 'package:flutter_test/flutter_test.dart';
import 'package:mvn_app/features/movie/data/repositories/movie_repository_impl.dart';

import '../../../../helpers/fakes.dart';

void main() {
  test('maps responses to entities', () async {
    final repository = MovieRepositoryImpl(FakeMovieSource());
    final movies = await repository.fetchTrending();
    expect(movies.single.title, 'Dune');
  });
}
