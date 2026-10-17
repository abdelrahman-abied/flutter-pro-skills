import 'package:dio/dio.dart';
import 'package:flutter/foundation.dart';
import 'package:riverpod_annotation/riverpod_annotation.dart';

import '../../features/auth/data/sources/token_storage.dart';
import 'auth_interceptor.dart';

part 'dio_provider.g.dart';

const apiBaseUrl = String.fromEnvironment('API_BASE_URL', defaultValue: 'https://api.shop.dev/v1');

@riverpod
Dio dio(Ref ref) {
  final dio = Dio(BaseOptions(baseUrl: apiBaseUrl, connectTimeout: const Duration(seconds: 10)));
  dio.interceptors.add(AuthInterceptor(ref.watch(tokenStorageProvider), refreshDio: Dio(BaseOptions(baseUrl: apiBaseUrl))));
  if (kDebugMode) {
    dio.interceptors.add(LogInterceptor(requestHeader: false, responseBody: false));
  }
  return dio;
}
