import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';

import '../../repository/models/weather.dart';
import '../../theme/cubit/theme_cubit.dart';
import '../bloc/weather_bloc.dart';

class WeatherPopulated extends StatelessWidget {
  const WeatherPopulated({
    super.key,
    required this.weather,
    required this.units,
    required this.onRefresh,
  });

  final Weather weather;
  final TemperatureUnits units;
  final RefreshCallback onRefresh;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final color = context.watch<ThemeCubit>().state;
    final temperature = units == TemperatureUnits.celsius
        ? weather.temperature
        : weather.temperature * 9 / 5 + 32;
    final symbol = units == TemperatureUnits.celsius ? '°C' : '°F';
    return DecoratedBox(
      decoration: BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topCenter,
          end: Alignment.bottomCenter,
          colors: [color, color.withValues(alpha: 0.4)],
        ),
      ),
      child: RefreshIndicator(
        onRefresh: onRefresh,
        child: ListView(
          padding: const EdgeInsets.only(top: 160),
          children: [
            Center(
              child: Column(
                children: [
                  Text(
                    weather.location,
                    style: theme.textTheme.displayMedium,
                  ),
                  Text(
                    '${temperature.toStringAsPrecision(2)}$symbol',
                    style: theme.textTheme.displaySmall,
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}
