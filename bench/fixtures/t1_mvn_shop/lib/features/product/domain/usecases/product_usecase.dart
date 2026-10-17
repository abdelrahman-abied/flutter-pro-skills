import 'package:riverpod_annotation/riverpod_annotation.dart';

import '../../data/repositories/product_repository_impl.dart';
import '../entities/product_entity.dart';
import '../repositories/product_repository.dart';

part 'product_usecase.g.dart';

class FetchProducts {
  const FetchProducts(this._repository);

  final ProductRepository _repository;

  Future<List<ProductEntity>> call({String? query}) =>
      _repository.fetchProducts(query: query);
}

class FetchProduct {
  const FetchProduct(this._repository);

  final ProductRepository _repository;

  Future<ProductEntity> call(int id) => _repository.fetchProduct(id);
}

@riverpod
FetchProducts fetchProducts(Ref ref) =>
    FetchProducts(ref.watch(productRepositoryProvider));

@riverpod
FetchProduct fetchProduct(Ref ref) =>
    FetchProduct(ref.watch(productRepositoryProvider));
