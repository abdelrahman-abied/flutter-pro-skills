import 'dart:developer' as developer;

import 'package:dio/dio.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../../../../core/logging/redact.dart';
import '../../domain/repositories/auth_repository.dart';
import '../sources/token_storage.dart';

final class AuthRepositoryImpl implements AuthRepository {
  AuthRepositoryImpl(this._dio, this._tokens, this._prefs);

  final Dio _dio;
  final TokenStorage _tokens;
  final SharedPreferences _prefs;

  @override
  Future<void> signIn({required String email, required String password}) async {
    final res = await _dio.post<Map<String, dynamic>>('/auth/login', data: {'email': email, 'password': password});
    final body = res.data ?? const {};
    final access = body['access_token'] as String;
    await _tokens.save(access: access, refresh: body['refresh_token'] as String);
    await _prefs.setString('last_email_domain', email.split('@').last);
    developer.log('signed in, status ${res.statusCode}, token ${redact(access)}');
  }

  @override
  Future<void> signOut() async {
    await _tokens.clear();
    await _prefs.clear();
  }
}
