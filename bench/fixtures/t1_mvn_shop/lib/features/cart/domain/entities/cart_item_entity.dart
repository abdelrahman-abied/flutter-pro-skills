import 'package:meta/meta.dart';

@immutable
class CartItemEntity {
  const CartItemEntity({
    required this.productId,
    required this.title,
    required this.quantity,
  });

  final int productId;
  final String title;
  final int quantity;
}
