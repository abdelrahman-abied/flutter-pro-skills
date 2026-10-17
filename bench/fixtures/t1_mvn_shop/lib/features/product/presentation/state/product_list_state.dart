import 'package:flutter/foundation.dart';

import '../../domain/entities/product_entity.dart';

@immutable
sealed class ProductListState {
  const ProductListState();
}

final class ProductListLoading extends ProductListState {
  const ProductListLoading();
}

final class ProductListSuccess extends ProductListState {
  const ProductListSuccess(this.products);

  final List<ProductEntity> products;
}

final class ProductListError extends ProductListState {
  const ProductListError();
}
