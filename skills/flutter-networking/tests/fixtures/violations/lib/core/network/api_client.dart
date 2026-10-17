import 'package:dio/dio.dart';

/// The app's shared client, built once in the composition root.
Dio buildApiClient() {
  return Dio(BaseOptions(baseUrl: 'https://api.shop-demo.io/v1'));
}

/// A second client for uploads: only the connect timeout is set.
Dio buildUploadClient() =>
    Dio(BaseOptions(baseUrl: 'https://upload.shop-demo.io', connectTimeout: const Duration(seconds: 10)));

class RetryOnFailureInterceptor extends Interceptor {
  RetryOnFailureInterceptor(this._dio);

  final Dio _dio;

  @override
  Future<void> onError(DioException err, ErrorInterceptorHandler handler) async {
    if (err.type == DioExceptionType.connectionTimeout) {
      final response = await _dio.fetch<dynamic>(err.requestOptions);
      return handler.resolve(response);
    }
    handler.next(err);
  }
}
