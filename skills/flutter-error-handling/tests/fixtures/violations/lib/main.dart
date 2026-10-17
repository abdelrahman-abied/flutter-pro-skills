import 'dart:async';

import 'package:flutter/material.dart';

import 'app.dart';

void main() {
  // ERR-013: binding initialized outside the zone that runs the app.
  WidgetsFlutterBinding.ensureInitialized();
  runZonedGuarded(() {
    runApp(const App());
  }, (error, stack) {
    debugPrint('uncaught: $error');
  });
  // ERR-012: no FlutterError.onError, although sentry_flutter is a dependency.
}
