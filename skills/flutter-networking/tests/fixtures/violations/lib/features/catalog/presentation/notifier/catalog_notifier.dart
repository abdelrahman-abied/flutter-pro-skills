import 'package:riverpod_annotation/riverpod_annotation.dart';

import '../../domain/entities/product.dart';
import '../../domain/usecases/load_products_usecase.dart';

part 'catalog_notifier.g.dart';

@riverpod
class CatalogNotifier extends _$CatalogNotifier {
  int _page = 0;

  @override
  List<Product> build() => const [];

  Future<void> loadMore() async {
    final next = await ref.read(loadProductsUseCaseProvider)(_page + 1);
    _page++;
    state = [...state, ...next];
  }
}

@riverpod
class CartNotifier extends _$CartNotifier {
  @override
  int build() => 0;
}

@riverpod
class FilterNotifier extends _$FilterNotifier {
  @override
  String build() => '';
}
