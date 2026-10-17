import 'package:riverpod_annotation/riverpod_annotation.dart';

import '../../domain/usecases/cart_usecase.dart';
import '../state/cart_state.dart';

part 'cart_notifier.g.dart';

@Riverpod(keepAlive: true)
class CartNotifier extends _$CartNotifier {
  @override
  CartState build() => const CartReady([]);

  Future<void> addItem({required int productId, required String title}) async {
    try {
      final items = await ref.read(addToCartProvider)(
        productId: productId,
        title: title,
      );
      state = CartReady(items);
    } catch (_) {}
  }
}
