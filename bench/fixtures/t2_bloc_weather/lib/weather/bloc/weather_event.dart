part of 'weather_bloc.dart';

sealed class WeatherEvent extends Equatable {
  const WeatherEvent();

  @override
  List<Object> get props => [];
}

final class WeatherRequested extends WeatherEvent {
  const WeatherRequested(this.city);

  final String city;

  @override
  List<Object> get props => [city];
}

final class WeatherRefreshed extends WeatherEvent {
  const WeatherRefreshed();
}

final class TemperatureUnitsToggled extends WeatherEvent {
  const TemperatureUnitsToggled();
}
