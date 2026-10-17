import 'package:riverpod_annotation/riverpod_annotation.dart';

import '../../../../core/error/app_exception.dart';
import '../../domain/usecases/product_usecase.dart';
import '../state/product_detail_state.dart';

part 'product_detail_notifier.g.dart';

@riverpod
class ProductDetailNotifier extends _$ProductDetailNotifier {
  @override
  ProductDetailState build(int productId) {
    Future.microtask(load);
    return const ProductDetailLoading();
  }

  Future<void> load() async {
    state = const ProductDetailLoading();
    try {
      final product = await ref.read(fetchProductProvider)(productId);
      state = ProductDetailSuccess(product);
    } on AppException {
      state = const ProductDetailError();
    }
  }
}
