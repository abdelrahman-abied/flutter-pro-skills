import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:google_fonts/google_fonts.dart';

import 'core/design_system/theme/app_theme.dart';
import 'settings/cubit/theme_cubit.dart';

void main() {
  GoogleFonts.config.allowRuntimeFetching = false;
  runApp(BlocProvider(create: (_) => ThemeCubit(), child: const App()));
}

class App extends StatelessWidget {
  const App({super.key});

  @override
  Widget build(BuildContext context) {
    // The app root may resolve ThemeMode.system itself.
    final systemDark = MediaQuery.platformBrightnessOf(context) == Brightness.dark;
    return BlocBuilder<ThemeCubit, ThemeMode>(
      builder: (context, mode) => MaterialApp(
        theme: AppTheme.light,
        darkTheme: AppTheme.dark,
        highContrastTheme: AppTheme.light,
        themeMode: systemDark ? mode : mode,
        home: const Placeholder(),
      ),
    );
  }
}

class DemoApp extends StatelessWidget {
  const DemoApp({super.key});

  @override
  Widget build(BuildContext context) {
    // Light-only on purpose: ThemeMode.light needs no darkTheme.
    return MaterialApp(
      theme: ThemeData(colorScheme: ColorScheme.fromSeed(seedColor: Colors.indigo)),
      themeMode: ThemeMode.light,
      home: const Placeholder(),
    );
  }
}
