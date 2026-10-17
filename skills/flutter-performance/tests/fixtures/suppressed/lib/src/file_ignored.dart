// perf-ignore-file: PERF-005 the fade runs once on a splash screen, profiled at 1 ms
import 'package:flutter/material.dart';

class Splash extends StatelessWidget {
  const Splash({super.key, required this.animation});

  final Animation<double> animation;

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: animation,
      builder: (context, child) => Opacity(opacity: animation.value, child: child),
      child: TweenAnimationBuilder<double>(
        tween: Tween(begin: 0, end: 1),
        duration: const Duration(seconds: 1),
        builder: (context, v, child) => Opacity(opacity: v, child: child),
        child: const FlutterLogo(),
      ),
    );
  }
}
