// GUARD: `XRepositoryImpl` is prescribed by Clean Architecture / MVN
// (noise-word-type must not fire).
import '../../domain/repositories/cart_repository.dart';
import '../sources/cart_api.dart';

class CartRepositoryImpl implements CartRepository {
  CartRepositoryImpl(this._api);

  final CartApi _api;

  @override
  Future<List<String>> fetchItems() => _api.getItems();
}
