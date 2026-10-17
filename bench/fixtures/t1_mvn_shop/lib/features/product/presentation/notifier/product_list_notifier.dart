import 'package:riverpod_annotation/riverpod_annotation.dart';

import '../../../../core/error/app_exception.dart';
import '../../domain/usecases/product_usecase.dart';
import '../state/product_list_state.dart';
import 'product_query_notifier.dart';

part 'product_list_notifier.g.dart';

@riverpod
class ProductListNotifier extends _$ProductListNotifier {
  @override
  ProductListState build() {
    final query = ref.watch(productQueryProvider);
    Future.microtask(() => load(query: query));
    return const ProductListLoading();
  }

  Future<void> load({String? query}) async {
    state = const ProductListLoading();
    try {
      final products = await ref.read(fetchProductsProvider)(query: query);
      state = ProductListSuccess(products);
    } on AppException {
      state = const ProductListError();
    }
  }

  Future<void> refresh() => load(query: ref.read(productQueryProvider));
}
