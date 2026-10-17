import 'package:flutter/animation.dart';

class MovieController {
  MovieController(this.anim);
  final AnimationController anim; // a Flutter controller as a field is fine
}

class MovieListVM {}

class FadeController extends AnimationController {
  FadeController({required super.vsync});
}
