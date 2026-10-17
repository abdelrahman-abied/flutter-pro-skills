import 'package:flutter/material.dart';

class Brand extends ThemeExtension<Brand> {
  const Brand({required this.accent});
  final Color accent;
  @override
  Brand copyWith({Color? accent}) => Brand(accent: accent ?? this.accent);
  @override
  Brand lerp(ThemeExtension<Brand>? other, double t) =>
      other is Brand ? Brand(accent: Color.lerp(accent, other.accent, t)!) : this;
}
