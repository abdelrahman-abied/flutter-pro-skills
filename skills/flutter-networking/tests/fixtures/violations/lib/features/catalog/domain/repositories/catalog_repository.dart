import '../entities/product.dart';

abstract interface class CatalogRepository {
  Future<List<Product>> page(int page);
}
