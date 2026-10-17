import 'package:dio/dio.dart';
import 'package:riverpod_annotation/riverpod_annotation.dart';

import '../../../../core/error/app_exception.dart';
import '../../../../core/network/api_client.dart';
import '../models/order_response.dart';

part 'order_remote_source.g.dart';

abstract interface class OrderRemoteSource {
  Future<List<OrderResponse>> fetchOrders();
}

class OrderRemoteSourceImpl implements OrderRemoteSource {
  const OrderRemoteSourceImpl(this._dio);

  final Dio _dio;

  @override
  Future<List<OrderResponse>> fetchOrders() async {
    try {
      final response = await _dio.get<List<dynamic>>('/orders');
      return response.data!
          .cast<Map<String, dynamic>>()
          .map(OrderResponse.fromJson)
          .toList();
    } on DioException catch (e) {
      throw AppException.fromDio(e);
    }
  }
}

@riverpod
OrderRemoteSource orderRemoteSource(Ref ref) =>
    OrderRemoteSourceImpl(ref.watch(apiClientProvider));
