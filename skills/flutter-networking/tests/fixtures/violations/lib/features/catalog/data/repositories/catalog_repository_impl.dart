import 'package:dio/dio.dart';

import '../../domain/entities/product.dart';
import '../../domain/repositories/catalog_repository.dart';
import '../sources/catalog_remote_source.dart';

class CatalogRepositoryImpl implements CatalogRepository {
  CatalogRepositoryImpl(this._source);

  final CatalogRemoteSource _source;
  final _pending = CancelToken();

  @override
  Future<List<Product>> page(int page) async {
    final rows = await _source.fetchProducts(page);
    return [for (final r in rows) Product(id: r['id'] as String, title: r['title'] as String)];
  }
}
