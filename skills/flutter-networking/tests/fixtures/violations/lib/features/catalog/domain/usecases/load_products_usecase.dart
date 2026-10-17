import 'package:riverpod_annotation/riverpod_annotation.dart';

import '../entities/product.dart';
import '../repositories/catalog_repository.dart';

class LoadProductsUseCase {
  LoadProductsUseCase(this._repository);

  final CatalogRepository _repository;

  Future<List<Product>> call(int page) => _repository.page(page);
}
