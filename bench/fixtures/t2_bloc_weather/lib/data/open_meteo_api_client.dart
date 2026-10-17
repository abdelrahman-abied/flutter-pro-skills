import 'dart:convert';

import 'package:http/http.dart' as http;

import 'models/location.dart';
import 'models/weather_reading.dart';

class LocationRequestFailure implements Exception {}

class LocationNotFoundFailure implements Exception {}

class WeatherRequestFailure implements Exception {}

class WeatherNotFoundFailure implements Exception {}

/// Dart API client which wraps the [Open-Meteo API](https://open-meteo.com).
class OpenMeteoApiClient {
  OpenMeteoApiClient({http.Client? httpClient})
      : _httpClient = httpClient ?? http.Client();

  static const _baseUrlWeather = 'api.open-meteo.com';
  static const _baseUrlGeocoding = 'geocoding-api.open-meteo.com';

  final http.Client _httpClient;

  /// Finds [Location]s matching `/v1/search/?name=(query)`.
  Future<List<Location>> locationSearch(String query, {int count = 1}) async {
    final request = Uri.https(
      _baseUrlGeocoding,
      '/v1/search',
      {'name': query, 'count': '$count'},
    );
    final response = await _httpClient.get(request);
    if (response.statusCode != 200) throw LocationRequestFailure();

    final json = jsonDecode(response.body) as Map<String, dynamic>;
    final results = json['results'] as List?;
    if (results == null || results.isEmpty) throw LocationNotFoundFailure();
    return results.cast<Map<String, dynamic>>().map(Location.fromJson).toList();
  }

  /// Fetches the current [WeatherReading] for a latitude and longitude.
  Future<WeatherReading> getWeather({
    required double latitude,
    required double longitude,
  }) async {
    final request = Uri.https(_baseUrlWeather, 'v1/forecast', {
      'latitude': '$latitude',
      'longitude': '$longitude',
      'current_weather': 'true',
    });
    final response = await _httpClient.get(request);
    if (response.statusCode != 200) throw WeatherRequestFailure();

    final json = jsonDecode(response.body) as Map<String, dynamic>;
    if (!json.containsKey('current_weather')) throw WeatherNotFoundFailure();
    return WeatherReading.fromJson(
      json['current_weather'] as Map<String, dynamic>,
    );
  }

  void close() => _httpClient.close();
}
