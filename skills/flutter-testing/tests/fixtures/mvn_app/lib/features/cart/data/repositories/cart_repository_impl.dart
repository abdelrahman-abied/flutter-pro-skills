import 'package:dio/dio.dart';
import 'package:riverpod_annotation/riverpod_annotation.dart';

import '../../domain/repositories/cart_repository.dart';
import '../sources/cart_api.dart';

part 'cart_repository_impl.g.dart';

class CartRepositoryImpl implements CartRepository {
  final CartApi _api;
  const CartRepositoryImpl(this._api);

  @override
  Future<int> total() async {
    try {
      return await _api.fetchTotal();
    } on DioException {
      return 0;
    }
  }

  @override
  Future<void> pay(int amount) => _api.pay(amount);
}

@riverpod
CartRepository cartRepository(Ref ref) => CartRepositoryImpl(CartApi(Dio()));
