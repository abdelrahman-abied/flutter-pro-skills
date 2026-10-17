import 'package:flutter/widgets.dart';

import 'app.dart';
import 'repository/weather_repository.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  runApp(WeatherApp(weatherRepository: WeatherRepository()));
}
