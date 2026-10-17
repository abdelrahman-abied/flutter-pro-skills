import 'package:flutter/foundation.dart';

class Settings {
  static const crashDsn = String.fromEnvironment('CRASH_DSN');
  static const devApiUrl = 'https://dev.tunnel.example';
  static const prodApiUrl = 'https://api.tunnel.example';
}

class Reporter {
  Reporter(this.forceReports);

  final bool forceReports;

  String get dsn => !kDebugMode || forceReports ? Settings.crashDsn : '';

  String get api => kDebugMode ? Settings.devApiUrl : Settings.prodApiUrl;
}
