import 'package:riverpod_annotation/riverpod_annotation.dart';

import '../../data/repositories/order_repository_impl.dart';
import '../entities/order_entity.dart';
import '../repositories/order_repository.dart';

part 'order_usecase.g.dart';

class FetchOrders {
  const FetchOrders(this._repository);

  final OrderRepository _repository;

  Future<List<OrderEntity>> call() => _repository.fetchOrders();
}

@riverpod
FetchOrders fetchOrders(Ref ref) =>
    FetchOrders(ref.watch(orderRepositoryProvider));
