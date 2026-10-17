// K2 C1: a concrete repository with no contract is normal in Bloc (role repository)
class ShoppingRepository {
  Future<List<String>> loadCatalog() async => const ['a'];
}
