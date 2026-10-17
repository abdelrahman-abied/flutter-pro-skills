import 'package:dio/dio.dart';
import 'package:riverpod_annotation/riverpod_annotation.dart';

import '../../../../core/error/app_exception.dart';
import '../../../../core/network/api_client.dart';
import '../models/profile_response.dart';

part 'profile_remote_source.g.dart';

abstract interface class ProfileRemoteSource {
  Future<ProfileResponse> fetchProfile();

  Future<ProfileResponse> updateName(String name);
}

class ProfileRemoteSourceImpl implements ProfileRemoteSource {
  const ProfileRemoteSourceImpl(this._dio);

  final Dio _dio;

  @override
  Future<ProfileResponse> fetchProfile() async {
    try {
      final response = await _dio.get<Map<String, dynamic>>('/me');
      return ProfileResponse.fromJson(response.data!);
    } on DioException catch (e) {
      throw AppException.fromDio(e);
    }
  }

  @override
  Future<ProfileResponse> updateName(String name) async {
    try {
      final response = await _dio.patch<Map<String, dynamic>>(
        '/me',
        data: {'name': name},
      );
      return ProfileResponse.fromJson(response.data!);
    } on DioException catch (e) {
      throw AppException.fromDio(e);
    }
  }
}

@riverpod
ProfileRemoteSource profileRemoteSource(Ref ref) =>
    ProfileRemoteSourceImpl(ref.watch(apiClientProvider));
