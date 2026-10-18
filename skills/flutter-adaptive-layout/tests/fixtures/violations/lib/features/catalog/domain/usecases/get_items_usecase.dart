import '../repositories/catalog_repository.dart';

class GetItemsUseCase {
  const GetItemsUseCase(this._repository);
  final CatalogRepository _repository;

  Future<List<String>> call() => _repository.items();
}
