import 'package:dio/dio.dart';

/// The API host written here and again in the bookings service (TP: NET-008 still fires).
class ApiService {
  ApiService()
      : _dio = Dio(BaseOptions(
          baseUrl: 'https://api.travel-demo.io',
          connectTimeout: const Duration(seconds: 5),
          receiveTimeout: const Duration(seconds: 10),
        ));

  final Dio _dio;

  Future<Response<dynamic>> continents() => _dio.get<dynamic>('/continent');
}
