import '../entities/cart_item_entity.dart';

abstract interface class CartRepository {
  Future<List<CartItemEntity>> addItem({
    required int productId,
    required String title,
  });
}
