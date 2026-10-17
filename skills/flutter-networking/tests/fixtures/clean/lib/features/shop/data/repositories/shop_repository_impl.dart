import '../../domain/entities/item.dart';
import '../../domain/repositories/shop_repository.dart';
import '../sources/shop_remote_source.dart';

class ShopRepositoryImpl implements ShopRepository {
  ShopRepositoryImpl(this._source);

  final ShopRemoteSource _source;

  @override
  Future<List<Item>> page(int page, {Object? cancelToken}) async {
    final rows = await _source.page(page);
    return [for (final r in rows.cast<Map<String, dynamic>>()) Item(id: '${r['id']}', name: '${r['name']}')];
  }

  @override
  Future<List<Item>> search(String query) async {
    final rows = await _source.search(query);
    return [for (final r in rows.cast<Map<String, dynamic>>()) Item(id: '${r['id']}', name: '${r['name']}')];
  }
}
