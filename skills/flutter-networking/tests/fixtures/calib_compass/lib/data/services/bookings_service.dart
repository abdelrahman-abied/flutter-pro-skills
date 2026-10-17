import 'package:dio/dio.dart';

class BookingsService {
  BookingsService(this._dio);

  final Dio _dio;

  Future<Response<dynamic>> all() => _dio.get<dynamic>('https://api.travel-demo.io/booking');
}
