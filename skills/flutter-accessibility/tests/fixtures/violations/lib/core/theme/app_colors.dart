import 'package:flutter/material.dart';

abstract final class AppColors {
  static const brand = Color(0xFFFFB74D);
  static const ink = Color(0xFF1B1B1F);

  static const light = ColorScheme(
    brightness: Brightness.light,
    primary: brand,
    onPrimary: Colors.white,
    secondary: ink,
    onSecondary: Colors.white,
    surface: Colors.white,
    onSurface: ink,
    error: Color(0xFFB3261E),
    onError: Colors.white,
  );
}
