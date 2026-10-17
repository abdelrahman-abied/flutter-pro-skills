import 'package:flutter/foundation.dart';

const int searchDepth = kDebugMode ? 12 : 18;
const Duration pollEvery = kReleaseMode ? Duration(seconds: 30) : Duration(seconds: 5);
final String crashDsn = !kDebugMode ? Environment.sentryDsn : '';
final String label = kDebugMode ? 'debug build' : '';

class Environment {
  static const sentryDsn = String.fromEnvironment('SENTRY_DSN');
}
