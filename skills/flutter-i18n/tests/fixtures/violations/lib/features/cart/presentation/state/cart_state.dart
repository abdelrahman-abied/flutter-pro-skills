sealed class CartState {
  const CartState();
}

final class CartEmpty extends CartState {
  const CartEmpty(this.message);
  final String message;
}
