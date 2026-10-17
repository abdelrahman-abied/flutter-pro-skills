import 'package:dio/dio.dart';

// role `repository` (concrete, no contract): ERR-004 and ERR-007 apply as for an impl.
class CartRepository {
  CartRepository(this._dio);
  final Dio _dio;

  Future<List<String>> items() async {
    final res = await _dio.get<List<String>>('/cart');
    return res.data ?? const [];
  }

  Future<String?> coupon() async {
    try {
      final res = await _dio.get<String>('/coupon');
      return res.data;
    } catch (e) {
      return null;
    }
  }
}
