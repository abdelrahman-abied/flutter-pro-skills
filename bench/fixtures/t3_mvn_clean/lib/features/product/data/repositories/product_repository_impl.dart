import 'package:riverpod_annotation/riverpod_annotation.dart';

import '../../domain/entities/product_entity.dart';
import '../../domain/repositories/product_repository.dart';
import '../sources/product_remote_source.dart';

part 'product_repository_impl.g.dart';

class ProductRepositoryImpl implements ProductRepository {
  const ProductRepositoryImpl(this._source);

  final ProductRemoteSource _source;

  @override
  Future<List<ProductEntity>> fetchProducts({String? query}) async {
    final responses = await _source.fetchProducts(query: query);
    return responses.map((r) => r.toEntity()).toList();
  }

  @override
  Future<ProductEntity> fetchProduct(int id) async =>
      (await _source.fetchProduct(id)).toEntity();
}

@riverpod
ProductRepository productRepository(Ref ref) =>
    ProductRepositoryImpl(ref.watch(productRemoteSourceProvider));
