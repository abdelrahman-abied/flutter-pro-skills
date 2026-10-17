import 'package:riverpod_annotation/riverpod_annotation.dart';

part 'product_query_notifier.g.dart';

/// The search text the product list is filtered by.
@riverpod
class ProductQueryNotifier extends _$ProductQueryNotifier {
  @override
  String build() => '';

  void update(String query) => state = query.trim();
}
