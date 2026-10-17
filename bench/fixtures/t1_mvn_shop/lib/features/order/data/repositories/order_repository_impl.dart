import 'package:riverpod_annotation/riverpod_annotation.dart';

import '../../domain/entities/order_entity.dart';
import '../../domain/repositories/order_repository.dart';
import '../sources/order_remote_source.dart';

part 'order_repository_impl.g.dart';

class OrderRepositoryImpl implements OrderRepository {
  const OrderRepositoryImpl(this._source);

  final OrderRemoteSource _source;

  @override
  Future<List<OrderEntity>> fetchOrders() async {
    final responses = await _source.fetchOrders();
    return responses.map((r) => r.toEntity()).toList();
  }
}

@riverpod
OrderRepository orderRepository(Ref ref) =>
    OrderRepositoryImpl(ref.watch(orderRemoteSourceProvider));
