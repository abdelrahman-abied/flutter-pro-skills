import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter/services.dart';

import '../config/app_config.dart';

class DevSettings {
  bool showPerf = false;
}

class App extends StatelessWidget {
  const App({super.key, required this.config});

  final AppConfig config;

  @override
  Widget build(BuildContext context) {
    assert(() {
      debugPaintSizeEnabled = true;
      return true;
    }());
    if (kDebugMode) {
      debugRepaintRainbowEnabled = true;
    }
    // debugPaintSizeEnabled = true;
    final settings = DevSettings();
    return MaterialApp(
      showPerformanceOverlay: kDebugMode && settings.showPerf,
      checkerboardRasterCacheImages: false,
      title: appFlavor == 'dev' ? 'Shop DEV' : 'Shop',
      home: const Text('kDebugMode ? devUrl : prodUrl'),
    );
  }
}
