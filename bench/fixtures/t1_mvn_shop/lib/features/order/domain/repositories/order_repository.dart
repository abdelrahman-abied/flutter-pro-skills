import '../entities/order_entity.dart';

abstract interface class OrderRepository {
  Future<List<OrderEntity>> fetchOrders();
}
