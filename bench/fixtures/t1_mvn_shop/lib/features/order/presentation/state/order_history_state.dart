import 'package:flutter/foundation.dart';

import '../../domain/entities/order_entity.dart';

@immutable
sealed class OrderHistoryState {
  const OrderHistoryState();
}

final class OrderHistoryLoading extends OrderHistoryState {
  const OrderHistoryLoading();
}

final class OrderHistorySuccess extends OrderHistoryState {
  const OrderHistorySuccess(this.orders);

  final List<OrderEntity> orders;
}

final class OrderHistoryError extends OrderHistoryState {
  const OrderHistoryError();
}
