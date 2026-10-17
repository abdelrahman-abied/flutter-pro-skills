import 'package:flutter/foundation.dart';

import '../../domain/entities/cart_item_entity.dart';

@immutable
sealed class CartState {
  const CartState();
}

final class CartReady extends CartState {
  const CartReady(this.items);

  final List<CartItemEntity> items;
}

final class CartError extends CartState {
  const CartError(this.items);

  final List<CartItemEntity> items;
}
