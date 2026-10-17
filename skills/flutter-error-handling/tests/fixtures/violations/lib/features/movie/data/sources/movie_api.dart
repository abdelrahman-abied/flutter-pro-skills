import 'package:dio/dio.dart';

/// Talks to the backend. Throws DioException (fine for a source).
class MovieApi {
  MovieApi(this._dio);

  final Dio _dio;
  int _failures = 0;

  Future<List<Map<String, dynamic>>> trending() async {
    final res = await _dio.get<List<dynamic>>('/trending');
    return res.data!.cast<Map<String, dynamic>>();
  }

  Future<void> ping() async {
    try {
      await _dio.get<void>('/ping');
    } catch (e) {}
  }

  Future<String> token() async {
    try {
      return (await _dio.get<String>('/token')).data!;
    } catch (_) {
      // Offline: callers treat an empty token as "not signed in".
      _failures++;
      return '';
    }
  }

  Future<String> session() async {
    try {
      return (await _dio.get<String>('/session')).data!;
    } catch (_) {
      _failures++;
      return 'anonymous';
    }
  }

  Future<void> legacy() async {
    try {
      await _dio.get<void>('/legacy');
    } catch (e) {
      throw e;
    }
  }

  void validate(String id) {
    if (id.isEmpty) throw 'id must not be empty';
  }

  int firstId(List<int> ids) {
    try {
      return ids.first;
    } on StateError {
      return -1;
    }
  }

  void report() => print(_failures);
}
