import 'package:dio/dio.dart';

/// Transport only: throws DioException / FormatException; the repository maps them.
class MovieApi {
  MovieApi(this._dio);

  final Dio _dio;

  Future<List<Map<String, dynamic>>> trending() async {
    final res = await _dio.get<List<dynamic>>('/trending');
    final data = res.data;
    if (data == null) throw const FormatException('empty body');
    return data.cast<Map<String, dynamic>>();
  }
}
