import 'package:dio/dio.dart';

/// Transport-independent failure the data layer throws upward.
sealed class AppException implements Exception {
  const AppException();

  factory AppException.fromDio(DioException e) {
    return switch (e.type) {
      DioExceptionType.connectionTimeout ||
      DioExceptionType.receiveTimeout ||
      DioExceptionType.sendTimeout ||
      DioExceptionType.connectionError =>
        const NetworkException(),
      DioExceptionType.badResponse when e.response?.statusCode == 401 =>
        const UnauthorizedException(),
      _ => const ServerException(),
    };
  }
}

final class NetworkException extends AppException {
  const NetworkException();
}

final class UnauthorizedException extends AppException {
  const UnauthorizedException();
}

final class ServerException extends AppException {
  const ServerException();
}
