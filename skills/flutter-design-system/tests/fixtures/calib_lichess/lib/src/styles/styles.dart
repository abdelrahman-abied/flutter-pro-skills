import 'package:flutter/material.dart';

@immutable
class const AppCustomColors({
  required final Color good,
  required final Color error,
}) extends ThemeExtension<AppCustomColors> {
  @override
  AppCustomColors copyWith({Color? good, Color? error}) =>
      AppCustomColors(good: good ?? this.good, error: error ?? this.error);

  @override
  AppCustomColors lerp(ThemeExtension<AppCustomColors>? other, double t) {
    return this;
  }

  AppCustomColors harmonized(ColorScheme scheme) => this;
}

const lichessCustomColors = AppCustomColors(good: Color(0xFF629924), error: Color(0xFFCC3333));

extension CustomColorsBuildContext on BuildContext {
  AppCustomColors get lichessColors => Theme.of(this).extension<AppCustomColors>()!;
}
