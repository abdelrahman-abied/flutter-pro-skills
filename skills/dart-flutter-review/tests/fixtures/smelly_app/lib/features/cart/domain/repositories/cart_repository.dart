// GUARD: clean repository contract.
abstract interface class CartRepository {
  Future<List<String>> fetchItems();
}
