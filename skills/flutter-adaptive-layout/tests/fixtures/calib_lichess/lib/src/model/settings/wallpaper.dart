import 'package:flutter/widgets.dart';
import 'package:freezed_annotation/freezed_annotation.dart';

part 'wallpaper.freezed.dart';

@freezed
class Wallpaper with _$Wallpaper {
  const Wallpaper._();
  const factory Wallpaper({required String path, required double scale}) = _Wallpaper;

  Matrix4 fitTo({required double viewportWidth, required double viewportHeight}) =>
      Matrix4.diagonal3Values(viewportWidth / scale, viewportHeight / scale, 1);
}
