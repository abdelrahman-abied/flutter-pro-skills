import '../entities/product_entity.dart';

abstract interface class ProductRepository {
  Future<List<ProductEntity>> fetchProducts({String? query});

  Future<ProductEntity> fetchProduct(int id);
}
