import 'dart:async';

import 'package:bloc/bloc.dart';
import 'package:flutter/material.dart';

import '../../repository/models/weather.dart';
import '../../weather/bloc/weather_bloc.dart';

class ThemeCubit extends Cubit<Color> {
  ThemeCubit({required WeatherBloc weatherBloc}) : super(defaultColor) {
    _weatherSubscription = weatherBloc.stream.listen((weatherState) {
      final weather = weatherState.weather;
      if (weatherState.status == WeatherStatus.success && weather != null) {
        emit(weather.toColor);
      }
    });
  }

  static const defaultColor = Color(0xFF2196F3);

  late final StreamSubscription<WeatherState> _weatherSubscription;

  @override
  Future<void> close() async {
    await _weatherSubscription.cancel();
    return super.close();
  }
}

extension on Weather {
  Color get toColor {
    switch (condition) {
      case WeatherCondition.clear:
        return Colors.orangeAccent;
      case WeatherCondition.snowy:
        return Colors.lightBlueAccent;
      case WeatherCondition.cloudy:
        return Colors.blueGrey;
      case WeatherCondition.rainy:
        return Colors.indigoAccent;
      case WeatherCondition.unknown:
        return ThemeCubit.defaultColor;
    }
  }
}
