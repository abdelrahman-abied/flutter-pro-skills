import 'package:flutter/material.dart';

abstract final class Dimens {
  const Dimens();
  static const paddingHorizontal = 20.0;
  static const paddingVertical = 24.0;
  double get paddingScreenHorizontal;
  double get profilePictureSize;
}

final class _DimensDesktop extends Dimens {
  @override
  final double paddingScreenHorizontal = 100.0;
  final double paddingScreenVertical = 64.0;
  @override
  final double profilePictureSize = 128.0;
  const _DimensDesktop();
}
