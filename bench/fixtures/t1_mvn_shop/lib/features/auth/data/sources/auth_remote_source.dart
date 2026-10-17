import 'package:dio/dio.dart';
import 'package:riverpod_annotation/riverpod_annotation.dart';

import '../../../../core/error/app_exception.dart';
import '../../../../core/network/api_client.dart';
import '../models/login_request.dart';
import '../models/login_response.dart';

part 'auth_remote_source.g.dart';

abstract interface class AuthRemoteSource {
  Future<LoginResponse> login(LoginRequest request);
}

class AuthRemoteSourceImpl implements AuthRemoteSource {
  const AuthRemoteSourceImpl(this._dio);

  final Dio _dio;

  @override
  Future<LoginResponse> login(LoginRequest request) async {
    try {
      final response = await _dio.post<Map<String, dynamic>>(
        '/login',
        data: request.toJson(),
      );
      return LoginResponse.fromJson(response.data!);
    } on DioException catch (e) {
      throw AppException.fromDio(e);
    }
  }
}

@riverpod
AuthRemoteSource authRemoteSource(Ref ref) =>
    AuthRemoteSourceImpl(ref.watch(apiClientProvider));
