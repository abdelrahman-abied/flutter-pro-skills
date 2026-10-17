import 'package:flutter/material.dart';

abstract final class AppColors {
  static const brand = Color(0xFF6750A4);
  static const ink = Color(0xFF1B1B1F);
  static const veil = Color(0x66FFFFFF);

  static const light = ColorScheme(
    brightness: Brightness.light,
    primary: brand,
    onPrimary: Colors.white,
    secondary: ink,
    onSecondary: Colors.white,
    tertiary: veil,
    onTertiary: Colors.white,
    surface: Colors.white,
    onSurface: ink,
    error: Color(0xFFB3261E),
    onError: Colors.white,
  );

  static ColorScheme seeded(Color seed) => ColorScheme.fromSeed(seedColor: seed, primary: seed);
}
