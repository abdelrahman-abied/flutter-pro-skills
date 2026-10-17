import 'package:flutter/material.dart';

enum WeatherCondition { clear, rainy }

extension on WeatherCondition {
  Color get toColor {
    switch (this) {
      case WeatherCondition.clear:
        return Colors.yellow;
      case WeatherCondition.rainy:
        return Colors.indigoAccent;
    }
  }
}

class WeatherApp extends StatelessWidget {
  const WeatherApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      theme: ThemeData(colorScheme: ColorScheme.fromSeed(seedColor: WeatherCondition.clear.toColor),
          textTheme: const TextTheme()),
      home: const Placeholder(),
    );
  }
}
