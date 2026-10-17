import '../entities/item.dart';

abstract interface class ShopRepository {
  Future<List<Item>> page(int page, {Object? cancelToken});
  Future<List<Item>> search(String query);
}
