import 'package:dio/dio.dart';

class CartApi {
  final Dio _dio;
  const CartApi(this._dio);

  Future<int> fetchTotal() async {
    final res = await _dio.get<Map<String, Object?>>('/cart');
    final data = res.data;
    if (data == null) return 0;
    final total = data['total'];
    return total is int ? total : int.tryParse('$total') ?? 0;
  }

  Future<void> pay(int amount) => _dio.post<void>('/pay', data: {'amount': amount});
}
