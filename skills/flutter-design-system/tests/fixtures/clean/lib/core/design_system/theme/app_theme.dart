import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

import '../tokens/app_colors.dart';

abstract final class AppTheme {
  static final ThemeData light = _build(Brightness.light, AppColors.light);
  static final ThemeData dark = _build(Brightness.dark, AppColors.dark);

  static ThemeData _build(Brightness brightness, AppColors colors) {
    final scheme = ColorScheme.fromSeed(seedColor: const Color(0xFF3355FF), brightness: brightness);
    return ThemeData(
      colorScheme: scheme,
      textTheme: GoogleFonts.interTextTheme(const TextTheme(bodyMedium: TextStyle(fontSize: 15))),
      filledButtonTheme: FilledButtonThemeData(
        style: FilledButton.styleFrom(shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12))),
      ),
      extensions: [colors],
    );
  }
}
