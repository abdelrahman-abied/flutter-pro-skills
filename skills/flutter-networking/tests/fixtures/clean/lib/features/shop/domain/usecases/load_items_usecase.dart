import '../entities/item.dart';
import '../repositories/shop_repository.dart';

class LoadItemsUseCase {
  LoadItemsUseCase(this._repository);

  final ShopRepository _repository;

  Future<List<Item>> call(int page) => _repository.page(page);
}
