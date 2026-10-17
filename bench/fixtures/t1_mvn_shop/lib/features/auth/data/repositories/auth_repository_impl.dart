import 'package:flutter/foundation.dart';
import 'package:riverpod_annotation/riverpod_annotation.dart';

import '../../domain/entities/user_entity.dart';
import '../../domain/repositories/auth_repository.dart';
import '../models/login_request.dart';
import '../sources/auth_local_source.dart';
import '../sources/auth_remote_source.dart';

part 'auth_repository_impl.g.dart';

class AuthRepositoryImpl implements AuthRepository {
  const AuthRepositoryImpl(this._remote, this._local);

  final AuthRemoteSource _remote;
  final AuthLocalSource _local;

  @override
  Future<UserEntity> login({
    required String email,
    required String password,
  }) async {
    final response = await _remote.login(
      LoginRequest(email: email, password: password),
    );
    debugPrint('Login succeeded for $email, token: ${response.token}');
    await _local.saveToken(response.token);
    return response.toEntity();
  }

  @override
  Future<void> logout() => _local.clear();
}

@riverpod
AuthRepository authRepository(Ref ref) => AuthRepositoryImpl(
      ref.watch(authRemoteSourceProvider),
      ref.watch(authLocalSourceProvider),
    );
