import 'dart:io';

import 'package:dio/dio.dart';
import 'package:dio/io.dart';
import 'package:riverpod_annotation/riverpod_annotation.dart';

import '../config/app_config.dart';

part 'api_client.g.dart';

@Riverpod(keepAlive: true)
Dio apiClient(Ref ref) {
  final dio = Dio(BaseOptions(
    baseUrl: AppConfig.production.apiBaseUrl,
    connectTimeout: const Duration(seconds: 10),
    receiveTimeout: const Duration(seconds: 20),
  ));
  dio.httpClientAdapter = IOHttpClientAdapter(
    createHttpClient: () {
      final client = HttpClient();
      client.findProxy = HttpClient.findProxyFromEnvironment;
      return client;
    },
  );
  dio.interceptors.add(AuthRefreshInterceptor(dio));
  dio.interceptors.add(SafeRetryInterceptor(dio));
  ref.onDispose(dio.close);
  return dio;
}

/// Configured after construction: both timeouts are set on .options.
Dio buildLegacyClient() {
  final dio = Dio();
  dio.options.connectTimeout = const Duration(seconds: 5);
  dio.options.receiveTimeout = const Duration(seconds: 15);
  return dio;
}

final _sharedOptions = BaseOptions(
  connectTimeout: const Duration(seconds: 5),
  receiveTimeout: const Duration(seconds: 5),
);

Dio buildReportsClient() => Dio(_sharedOptions);

/// Replays a request rejected with 401 after refreshing the token (flutter-secure-defaults owns refresh).
class AuthRefreshInterceptor extends QueuedInterceptor {
  AuthRefreshInterceptor(this._dio);

  final Dio _dio;

  @override
  Future<void> onError(DioException err, ErrorInterceptorHandler handler) async {
    if (err.response?.statusCode == 401) {
      final retried = await _dio.fetch<dynamic>(err.requestOptions);
      return handler.resolve(retried);
    }
    handler.next(err);
  }
}

class SafeRetryInterceptor extends Interceptor {
  SafeRetryInterceptor(this._dio);

  final Dio _dio;
  static const _idempotent = {'GET', 'HEAD', 'PUT', 'DELETE', 'OPTIONS'};

  @override
  Future<void> onError(DioException err, ErrorInterceptorHandler handler) async {
    final transient = err.type == DioExceptionType.connectionTimeout;
    if (transient && _idempotent.contains(err.requestOptions.method)) {
      return handler.resolve(await _dio.fetch<dynamic>(err.requestOptions));
    }
    handler.next(err);
  }
}
