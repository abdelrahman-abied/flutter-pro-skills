part of 'weather_bloc.dart';

enum WeatherStatus { initial, loading, success, failure }

enum TemperatureUnits { fahrenheit, celsius }

final class WeatherState extends Equatable {
  const WeatherState({
    this.status = WeatherStatus.initial,
    this.temperatureUnits = TemperatureUnits.celsius,
    this.weather,
  });

  final WeatherStatus status;
  final TemperatureUnits temperatureUnits;
  final Weather? weather;

  WeatherState copyWith({
    WeatherStatus? status,
    TemperatureUnits? temperatureUnits,
    Weather? weather,
  }) {
    return WeatherState(
      status: status ?? this.status,
      temperatureUnits: temperatureUnits ?? this.temperatureUnits,
      weather: weather ?? this.weather,
    );
  }

  @override
  List<Object?> get props => [status, temperatureUnits, weather];
}
