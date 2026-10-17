import 'package:flutter/material.dart';

class WeatherBackground extends StatelessWidget {
  const WeatherBackground({super.key});

  @override
  Widget build(BuildContext context) {
    final color = Theme.of(context).colorScheme.primary;
    return Column(
      children: [
        ColoredBox(color: color.brighten()),
        const Text('🏙️', style: TextStyle(fontSize: 64)),
        const Text('Updated', style: TextStyle(fontSize: 13)),
      ],
    );
  }
}

extension on Color {
  Color brighten([int percent = 10]) {
    final p = percent / 100;
    final alpha = (a * 255).round();
    final red = (r * 255).round();
    final green = (g * 255).round();
    final blue = (b * 255).round();
    return Color.fromARGB(alpha, red + ((255 - red) * p).round(), green + ((255 - green) * p).round(),
        blue + ((255 - blue) * p).round());
  }
}
