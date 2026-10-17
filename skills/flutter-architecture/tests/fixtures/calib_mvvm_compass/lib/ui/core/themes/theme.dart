// K1 A5: statics that are never reassigned -> ARCH-105 low; a reassigned one stays medium
import 'package:flutter/material.dart';

abstract final class AppTheme {
  static ThemeData lightTheme = ThemeData();
  static int counter = 0;
  static void bump() => counter++;
}
