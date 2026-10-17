enum CartFailure { network, unknown }

sealed class CartState {
  const CartState();
}

final class CartLoaded extends CartState {
  const CartLoaded(this.count, this.total);
  final int count;
  final double total;
}

final class CartError extends CartState {
  const CartError(this.failure);
  final CartFailure failure;
}
