import 'package:dio/dio.dart';

import '../../features/auth/data/sources/token_storage.dart';

/// Adds the bearer token and refreshes it once on 401. QueuedInterceptor runs one refresh at a time.
final class AuthInterceptor extends QueuedInterceptor {
  AuthInterceptor(this._storage, {required Dio refreshDio}) : _refreshDio = refreshDio;

  final TokenStorage _storage;
  final Dio _refreshDio; // no AuthInterceptor on it: a failing refresh must not recurse

  @override
  Future<void> onRequest(RequestOptions options, RequestInterceptorHandler handler) async {
    final access = await _storage.readAccessToken();
    if (access != null) options.headers['Authorization'] = 'Bearer $access';
    handler.next(options);
  }

  @override
  Future<void> onError(DioException err, ErrorInterceptorHandler handler) async {
    if (err.response?.statusCode != 401 || err.requestOptions.extra['retried'] == true) {
      return handler.next(err);
    }
    final refresh = await _storage.readRefreshToken();
    if (refresh == null) return handler.next(err);
    try {
      final res = await _refreshDio.post<Map<String, dynamic>>('/auth/refresh', data: {'refresh_token': refresh});
      final body = res.data ?? const {};
      await _storage.save(access: body['access_token'] as String, refresh: body['refresh_token'] as String);
      final retry = err.requestOptions..extra['retried'] = true;
      handler.resolve(await _refreshDio.fetch<Object?>(retry));
    } on DioException {
      await _storage.clear(); // refresh failed: sign out everywhere
      handler.next(err);
    }
  }
}
