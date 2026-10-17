import 'package:dio/dio.dart';

class HomeProvider {
  HomeProvider(this._dio);
  final Dio _dio;

  Future<String> title() async => (await _dio.get<String>('/title')).data ?? '';
}
