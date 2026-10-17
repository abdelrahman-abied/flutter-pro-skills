import 'package:flutter/material.dart';

final appTheme = ThemeData(colorScheme: const ColorScheme.light(primary: Color(0xFFE4935D)), textTheme: const TextTheme());

class _Corners {
  late final double sm = 4;
  late final double md = 8;
  late final double lg = 32;
}

class _Insets {
  _Insets(this._scale);
  final double _scale;
  late final double xs = 8 * _scale;
  late final double sm = 16 * _scale;
  late final double md = 24 * _scale;
  late final double lg = 32 * _scale;
}
