import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';

import 'app/app.dart';
import 'config/app_config.dart';

void main() {
  final config = AppConfig.forFlavor(appFlavor ?? 'dev');
  runApp(App(config: config));
}
