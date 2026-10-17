class CartState {
  CartState(this.items);
  List<String> items; // ARCH-106
  final bool shouldNavigateToCheckout = false; // ARCH-111
}
