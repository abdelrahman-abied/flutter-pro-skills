import 'package:dio/dio.dart';
import 'package:riverpod_annotation/riverpod_annotation.dart';

import '../../../../core/error/app_exception.dart';
import '../../../../core/network/api_client.dart';
import '../models/cart_item_request.dart';
import '../models/cart_item_response.dart';

part 'cart_remote_source.g.dart';

abstract interface class CartRemoteSource {
  Future<List<CartItemResponse>> addItem(CartItemRequest request);
}

class CartRemoteSourceImpl implements CartRemoteSource {
  const CartRemoteSourceImpl(this._dio);

  final Dio _dio;

  @override
  Future<List<CartItemResponse>> addItem(CartItemRequest request) async {
    try {
      final response = await _dio.post<List<dynamic>>(
        '/cart/items',
        data: request.toJson(),
      );
      return response.data!
          .cast<Map<String, dynamic>>()
          .map(CartItemResponse.fromJson)
          .toList();
    } on DioException catch (e) {
      throw AppException.fromDio(e);
    }
  }
}

@riverpod
CartRemoteSource cartRemoteSource(Ref ref) =>
    CartRemoteSourceImpl(ref.watch(apiClientProvider));
