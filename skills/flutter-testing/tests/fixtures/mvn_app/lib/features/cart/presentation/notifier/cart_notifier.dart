import 'package:riverpod_annotation/riverpod_annotation.dart';

import '../../domain/usecases/cart_usecase.dart';
import '../../domain/usecases/checkout_usecase.dart';

part 'cart_notifier.g.dart';

@riverpod
class CartNotifier extends _$CartNotifier {
  @override
  Future<int> build() => ref.watch(getCartTotalProvider)();

  Future<bool> checkout({required bool acceptedTerms}) async {
    try {
      await ref.read(checkoutProvider)(acceptedTerms: acceptedTerms);
      ref.invalidateSelf();
      return true;
    } on CheckoutException catch (e) {
      if (e.reason == 'terms' || e.reason == 'limit') return false;
      rethrow;
    }
  }
}
