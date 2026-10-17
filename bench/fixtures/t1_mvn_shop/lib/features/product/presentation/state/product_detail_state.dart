import 'package:flutter/foundation.dart';

import '../../domain/entities/product_entity.dart';

@immutable
sealed class ProductDetailState {
  const ProductDetailState();
}

final class ProductDetailLoading extends ProductDetailState {
  const ProductDetailLoading();
}

final class ProductDetailSuccess extends ProductDetailState {
  const ProductDetailSuccess(this.product);

  final ProductEntity product;
}

final class ProductDetailError extends ProductDetailState {
  const ProductDetailError();
}
