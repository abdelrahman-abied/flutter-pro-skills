import 'package:flutter/material.dart';

class ChartColors extends ThemeExtension<ChartColors> {
  const ChartColors({required this.line});

  final Color line;

  @override
  ChartColors copyWith({Color? line}) => ChartColors(line: line ?? this.line);

  @override
  ChartColors lerp(ThemeExtension<ChartColors>? other, double t) {
    if (other is! ChartColors) return this;
    return ChartColors(line: Color.lerp(line, other.line, t)!);
  }
}
