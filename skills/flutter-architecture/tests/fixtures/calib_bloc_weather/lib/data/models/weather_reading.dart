import 'package:equatable/equatable.dart';

class WeatherReading extends Equatable {
  const WeatherReading({required this.temperature, required this.weatherCode});

  factory WeatherReading.fromJson(Map<String, dynamic> json) => WeatherReading(
        temperature: (json['temperature'] as num).toDouble(),
        weatherCode: (json['weathercode'] as num).toInt(),
      );

  final double temperature;
  final int weatherCode;

  @override
  List<Object> get props => [temperature, weatherCode];
}
