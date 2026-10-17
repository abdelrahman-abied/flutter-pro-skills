import 'package:riverpod_annotation/riverpod_annotation.dart';

import '../../data/repositories/cart_repository_impl.dart';
import '../entities/cart_item_entity.dart';
import '../repositories/cart_repository.dart';

part 'cart_usecase.g.dart';

class AddToCart {
  const AddToCart(this._repository);

  final CartRepository _repository;

  Future<List<CartItemEntity>> call({
    required int productId,
    required String title,
  }) =>
      _repository.addItem(productId: productId, title: title);
}

@riverpod
AddToCart addToCart(Ref ref) => AddToCart(ref.watch(cartRepositoryProvider));
