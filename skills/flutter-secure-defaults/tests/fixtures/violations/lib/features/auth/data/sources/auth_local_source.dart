import 'package:dio/dio.dart';
import 'package:hive/hive.dart';
import 'package:shared_preferences/shared_preferences.dart';

// SEC-001 x2 (prefs + Hive); SEC-011 (response body logged in an auth source).
class AuthLocalSource {
  AuthLocalSource(this._prefs, this._box, this._dio);

  final SharedPreferences _prefs;
  final Box<String> _box;
  final Dio _dio;

  Future<void> saveSession(String token, String refresh) async {
    await _prefs.setString('access_token', token);
    await _box.put('refresh_token', refresh);
    // Not reported: timestamps and settings.
    await _prefs.setString('token_expiry', DateTime.now().toIso8601String());
    await _prefs.setString('theme_mode', 'dark');
  }

  Future<void> login(String user) async {
    final response = await _dio.post<Map<String, dynamic>>('/login', data: {'user': user});
    print('login response: ${response.data}');
  }
}
