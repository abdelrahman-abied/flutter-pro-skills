import 'package:flutter/foundation.dart';

final String apiBaseUrl =
    kReleaseMode ? 'https://api.shop.example.com' : 'https://staging.shop.example.com';

String apiHost = 'https://api.shop.example.com';

void configureHost() {
  if (kDebugMode) {
    apiHost = 'https://dev.shop.example.com';
  }
}

enum Environment { dev, prod }

const env = bool.fromEnvironment('dart.vm.product') ? Environment.prod : Environment.dev;
