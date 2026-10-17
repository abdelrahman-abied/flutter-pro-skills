import 'dart:io';

import 'package:dio/dio.dart';
import 'package:dio/io.dart';

// SEC-003: cleartext base URL; SEC-005: LogInterceptor with default headers; SEC-006: block-body accept-all.
Dio buildDio() {
  final dio = Dio(BaseOptions(baseUrl: 'http://api.shop-backend.com/v1'));
  dio.interceptors.add(LogInterceptor(requestBody: true));
  (dio.httpClientAdapter as IOHttpClientAdapter).createHttpClient = () {
    final client = HttpClient();
    client.badCertificateCallback = (cert, host, port) {
      return true;
    };
    return client;
  };
  return dio;
}

// Not reported: local and emulator hosts, XML namespaces, a scheme check.
const devUrl = 'http://10.0.2.2:8080';
const svgNs = 'http://www.w3.org/2000/svg';
bool isPlain(String url) => url.startsWith('http://');
