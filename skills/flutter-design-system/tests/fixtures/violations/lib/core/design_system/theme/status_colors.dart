import 'package:flutter/material.dart';

class StatusColors extends ThemeExtension<StatusColors> {
  StatusColors({required this.warning, required this.danger});

  Color warning;
  final Color danger;

  static final light = StatusColors(warning: const Color(0xFFFFA000), danger: const Color(0xFFD32F2F));
  static final dark = StatusColors(warning: const Color(0xFFFFCA28), danger: const Color(0xFFEF5350));

  @override
  StatusColors copyWith({Color? warning, Color? danger}) =>
      StatusColors(warning: warning ?? this.warning, danger: danger ?? this.danger);

  @override
  StatusColors lerp(ThemeExtension<StatusColors>? other, double t) {
    return this;
  }
}
