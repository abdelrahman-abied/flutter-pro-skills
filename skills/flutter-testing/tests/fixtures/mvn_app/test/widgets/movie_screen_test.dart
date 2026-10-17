import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mvn_app/features/movie/data/sources/movie_source.dart';
import 'package:mvn_app/features/movie/presentation/view/movie_view.dart';
import 'package:mvn_app/features/movie/presentation/widget/movie_list.dart';

import '../helpers/fakes.dart';

void main() {
  testWidgets('shows the list once loaded', (tester) async {
    await tester.pumpWidget(
      ProviderScope(
        overrides: [movieSourceProvider.overrideWithValue(FakeMovieSource())],
        child: const MaterialApp(home: MovieView()),
      ),
    );
    await tester.pump();
    expect(find.byType(MovieList), findsOneWidget);
  });
}
