import 'package:dio/dio.dart';
import 'package:riverpod_annotation/riverpod_annotation.dart';

part 'api_client.g.dart';

const _baseUrl = 'https://api.catalog.example.com/v1';

@Riverpod(keepAlive: true)
Dio apiClient(Ref ref) {
  return Dio(
    BaseOptions(
      baseUrl: _baseUrl,
      connectTimeout: const Duration(seconds: 10),
      receiveTimeout: const Duration(seconds: 15),
    ),
  );
}
