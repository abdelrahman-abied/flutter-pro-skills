import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mvn_app/features/movie/data/sources/movie_source.dart';
import 'package:mvn_app/features/movie/presentation/notifier/movie_notifier.dart';
import 'package:mvn_app/features/movie/presentation/state/movie_state.dart';

import '../helpers/fakes.dart';

void main() {
  late ProviderContainer container;

  setUp(() {
    container = ProviderContainer(
      overrides: [movieSourceProvider.overrideWithValue(FakeMovieSource())],
    );
    addTearDown(container.dispose);
  });

  test('load emits success with the trending movies', () async {
    await container.read(movieNotifierProvider.notifier).load();
    expect(container.read(movieNotifierProvider), isA<MovieSuccess>());
  });
}
