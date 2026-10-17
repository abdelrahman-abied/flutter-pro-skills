// SMELLS: i-prefixed-interface, noise-word-type, get-prefixed-method,
// async-suffix, swallowed-catch, then-chain (countItems; warmUp's fire-and-forget
// statement in a sync method is a guard and must NOT be reported).
import 'package:dio/dio.dart';

abstract class ICartApi {
  Future<List<String>> getItems();
}

class CartManager {
  final List<String> items = [];
}

class CartApi implements ICartApi {
  CartApi(this._dio);

  final Dio _dio;

  @override
  Future<List<String>> getItems() async {
    try {
      final response = await _dio.get<List<String>>('/cart');
      return response.data ?? const [];
    } catch (e) {
      return const [];
    }
  }

  Future<void> syncAsync() async {
    try {
      await _dio.post<void>('/cart/sync');
    } catch (e) {}
  }

  void warmUp() {
    getItems().then((items) => items.length);
  }

  Future<int> countItems() => getItems().then((items) => items.length);
}
