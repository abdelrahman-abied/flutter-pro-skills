import '../../domain/entities/cart_item_entity.dart';

class CartItemResponse {
  const CartItemResponse({
    required this.productId,
    required this.title,
    required this.quantity,
  });

  factory CartItemResponse.fromJson(Map<String, dynamic> json) =>
      CartItemResponse(
        productId: json['product_id'] as int,
        title: json['title'] as String,
        quantity: json['quantity'] as int,
      );

  final int productId;
  final String title;
  final int quantity;

  CartItemEntity toEntity() =>
      CartItemEntity(productId: productId, title: title, quantity: quantity);
}
