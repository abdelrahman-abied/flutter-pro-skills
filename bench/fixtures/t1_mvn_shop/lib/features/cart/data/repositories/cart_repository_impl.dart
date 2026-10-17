import 'package:riverpod_annotation/riverpod_annotation.dart';

import '../../domain/entities/cart_item_entity.dart';
import '../../domain/repositories/cart_repository.dart';
import '../models/cart_item_request.dart';
import '../sources/cart_remote_source.dart';

part 'cart_repository_impl.g.dart';

class CartRepositoryImpl implements CartRepository {
  const CartRepositoryImpl(this._source);

  final CartRemoteSource _source;

  @override
  Future<List<CartItemEntity>> addItem({
    required int productId,
    required String title,
  }) async {
    final items = await _source.addItem(
      CartItemRequest(productId: productId, quantity: 1),
    );
    return items.map((i) => i.toEntity()).toList();
  }
}

@riverpod
CartRepository cartRepository(Ref ref) =>
    CartRepositoryImpl(ref.watch(cartRemoteSourceProvider));
