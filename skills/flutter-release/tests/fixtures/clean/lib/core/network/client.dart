import 'package:flutter/foundation.dart';

class Interceptors {
  final list = <Object>[];
}

class ApiClient {
  ApiClient(this.baseUrl) {
    if (kDebugMode) {
      interceptors.list.add('logger');
    }
  }

  final String baseUrl;
  final interceptors = Interceptors();
}
