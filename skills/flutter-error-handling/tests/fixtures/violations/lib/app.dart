import 'package:flutter/material.dart';

import 'features/movie/presentation/view/movie_view.dart';

class App extends StatelessWidget {
  const App({super.key});

  @override
  Widget build(BuildContext context) => const MaterialApp(home: MovieView());
}
