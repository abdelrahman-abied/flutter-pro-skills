import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'core/theme/app_theme.dart';
import 'features/movie/presentation/view/movie_view.dart';

void main() => runApp(const ProviderScope(child: App()));

class App extends StatelessWidget {
  const App({super.key});

  @override
  Widget build(BuildContext context) =>
      MaterialApp(theme: appTheme, home: const MovieView());
}
