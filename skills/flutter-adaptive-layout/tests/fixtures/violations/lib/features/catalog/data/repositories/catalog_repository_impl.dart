import '../../domain/repositories/catalog_repository.dart';

class CatalogRepositoryImpl implements CatalogRepository {
  @override
  Future<List<String>> items() async => const ['a', 'b'];
}
