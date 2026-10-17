import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';

import 'repository/weather_repository.dart';
import 'weather/view/weather_page.dart';

class WeatherApp extends StatelessWidget {
  const WeatherApp({required WeatherRepository weatherRepository, super.key})
      : _weatherRepository = weatherRepository;

  final WeatherRepository _weatherRepository;

  @override
  Widget build(BuildContext context) {
    return RepositoryProvider.value(
      value: _weatherRepository,
      child: MaterialApp(
        theme: ThemeData(useMaterial3: true),
        home: const WeatherPage(),
      ),
    );
  }
}
