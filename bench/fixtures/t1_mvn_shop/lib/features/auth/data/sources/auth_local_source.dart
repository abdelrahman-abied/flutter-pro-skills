import 'package:riverpod_annotation/riverpod_annotation.dart';
import 'package:shared_preferences/shared_preferences.dart';

part 'auth_local_source.g.dart';

abstract interface class AuthLocalSource {
  Future<void> saveToken(String token);

  Future<String?> readToken();

  Future<void> clear();
}

class AuthLocalSourceImpl implements AuthLocalSource {
  const AuthLocalSourceImpl();

  static const _tokenKey = 'auth_token';

  @override
  Future<void> saveToken(String token) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_tokenKey, token);
  }

  @override
  Future<String?> readToken() async {
    final prefs = await SharedPreferences.getInstance();
    return prefs.getString(_tokenKey);
  }

  @override
  Future<void> clear() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove(_tokenKey);
  }
}

@riverpod
AuthLocalSource authLocalSource(Ref ref) => const AuthLocalSourceImpl();
