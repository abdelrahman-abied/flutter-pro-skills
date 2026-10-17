import 'package:bloc/bloc.dart';
import 'package:equatable/equatable.dart';

import '../../repository/models/weather.dart';
import '../../repository/weather_repository.dart';

part 'weather_event.dart';
part 'weather_state.dart';

class WeatherBloc extends Bloc<WeatherEvent, WeatherState> {
  WeatherBloc(this._weatherRepository) : super(const WeatherState()) {
    on<WeatherRequested>(_onWeatherRequested);
    on<WeatherRefreshed>(_onWeatherRefreshed);
    on<TemperatureUnitsToggled>(_onTemperatureUnitsToggled);
  }

  final WeatherRepository _weatherRepository;

  Future<void> _onWeatherRequested(
    WeatherRequested event,
    Emitter<WeatherState> emit,
  ) async {
    if (event.city.isEmpty) return;
    emit(state.copyWith(status: WeatherStatus.loading));
    try {
      final weather = await _weatherRepository.getWeather(event.city);
      emit(state.copyWith(status: WeatherStatus.success, weather: weather));
    } on Exception {
      emit(state.copyWith(status: WeatherStatus.failure));
    }
  }

  Future<void> _onWeatherRefreshed(
    WeatherRefreshed event,
    Emitter<WeatherState> emit,
  ) async {
    final current = state.weather;
    if (state.status != WeatherStatus.success || current == null) return;
    try {
      final weather = await _weatherRepository.getWeather(current.location);
      emit(state.copyWith(status: WeatherStatus.success, weather: weather));
    } on Exception {
      emit(state);
    }
  }

  void _onTemperatureUnitsToggled(
    TemperatureUnitsToggled event,
    Emitter<WeatherState> emit,
  ) {
    emit(
      state.copyWith(
        temperatureUnits: state.temperatureUnits == TemperatureUnits.celsius
            ? TemperatureUnits.fahrenheit
            : TemperatureUnits.celsius,
      ),
    );
  }
}
