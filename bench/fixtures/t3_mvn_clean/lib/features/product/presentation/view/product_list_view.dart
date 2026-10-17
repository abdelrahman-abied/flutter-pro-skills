import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../../l10n/gen/app_localizations.dart';
import '../notifier/product_list_notifier.dart';
import '../notifier/product_query_notifier.dart';
import '../state/product_list_state.dart';
import '../widget/product_search_bar.dart';
import '../widget/product_tile.dart';

class ProductListView extends ConsumerWidget {
  const ProductListView({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final l10n = AppLocalizations.of(context)!;
    final state = ref.watch(productListProvider);

    return Scaffold(
      appBar: AppBar(
        title: Text(l10n.productsTitle),
      ),
      body: Column(
        children: [
          ProductSearchBar(
            onSearch: ref.read(productQueryProvider.notifier).update,
          ),
          Expanded(
            child: RefreshIndicator(
              onRefresh: ref.read(productListProvider.notifier).refresh,
              child: switch (state) {
                ProductListLoading() =>
                  const Center(child: CircularProgressIndicator()),
                ProductListError() => Center(
                    child: TextButton(
                      onPressed: ref.read(productListProvider.notifier).refresh,
                      child: Text(l10n.retry),
                    ),
                  ),
                ProductListSuccess(:final products) => ListView.builder(
                    itemCount: products.length,
                    itemBuilder: (context, i) => ProductTile(
                      product: products[i],
                    ),
                  ),
              },
            ),
          ),
        ],
      ),
    );
  }
}
