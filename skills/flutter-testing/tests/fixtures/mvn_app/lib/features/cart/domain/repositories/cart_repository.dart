abstract interface class CartRepository {
  Future<int> total();
  Future<void> pay(int amount);
}
