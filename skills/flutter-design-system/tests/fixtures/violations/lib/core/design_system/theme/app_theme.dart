import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

import 'app_colors.dart';
import 'status_colors.dart';

abstract final class AppTheme {
  static final ThemeData light = ThemeData(
    colorScheme: ColorScheme.fromSeed(seedColor: const Color(0xFF3355FF)),
    textTheme: GoogleFonts.interTextTheme(),
    extensions: const [AppColors.light, StatusColors.light],
  );

  static final ThemeData dark = ThemeData(
    colorScheme: ColorScheme.fromSeed(seedColor: const Color(0xFF3355FF), brightness: Brightness.dark),
    textTheme: GoogleFonts.interTextTheme(),
    extensions: const [StatusColors.dark],
  );
}
