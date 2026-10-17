class CartItemRequest {
  const CartItemRequest({required this.productId, required this.quantity});

  final int productId;
  final int quantity;

  Map<String, dynamic> toJson() =>
      {'product_id': productId, 'quantity': quantity};
}
