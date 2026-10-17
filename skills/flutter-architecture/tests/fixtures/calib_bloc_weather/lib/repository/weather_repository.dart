import '../data/open_meteo_api_client.dart';
import 'models/weather.dart';

class WeatherRepository {
  WeatherRepository({OpenMeteoApiClient? weatherApiClient})
      : _weatherApiClient = weatherApiClient ?? OpenMeteoApiClient();

  final OpenMeteoApiClient _weatherApiClient;

  Future<Weather> getWeather(String city) async {
    final location = (await _weatherApiClient.locationSearch(city)).first;
    final reading = await _weatherApiClient.getWeather(
      latitude: location.latitude,
      longitude: location.longitude,
    );
    return Weather(
      location: location.name,
      temperature: reading.temperature,
      condition: reading.weatherCode.toCondition,
    );
  }

  void dispose() => _weatherApiClient.close();
}

extension on int {
  WeatherCondition get toCondition {
    switch (this) {
      case 0:
        return WeatherCondition.clear;
      case 1:
      case 2:
      case 3:
      case 45:
      case 48:
        return WeatherCondition.cloudy;
      case 51:
      case 53:
      case 55:
      case 61:
      case 63:
      case 65:
      case 80:
      case 81:
      case 82:
        return WeatherCondition.rainy;
      case 71:
      case 73:
      case 75:
      case 77:
      case 85:
      case 86:
        return WeatherCondition.snowy;
      default:
        return WeatherCondition.unknown;
    }
  }
}
