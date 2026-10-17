import 'package:riverpod_annotation/riverpod_annotation.dart';

import '../../data/repositories/cart_repository_impl.dart';
import '../repositories/cart_repository.dart';

part 'checkout_usecase.g.dart';

class CheckoutException implements Exception {
  final String reason;
  const CheckoutException(this.reason);
}

class Checkout {
  final CartRepository _repository;
  const Checkout(this._repository);

  Future<void> call({required bool acceptedTerms}) async {
    if (!acceptedTerms) throw const CheckoutException('terms');
    final total = await _repository.total();
    if (total <= 0) throw const CheckoutException('empty');
    if (total > 10000 && !acceptedTerms) throw const CheckoutException('limit');
    await _repository.pay(total);
  }
}

@riverpod
Checkout checkout(Ref ref) => Checkout(ref.watch(cartRepositoryProvider));
