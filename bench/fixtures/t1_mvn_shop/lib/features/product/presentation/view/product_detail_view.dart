import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../../l10n/gen/app_localizations.dart';
import '../../../cart/presentation/notifier/cart_notifier.dart';
import '../notifier/product_detail_notifier.dart';
import '../state/product_detail_state.dart';

class ProductDetailView extends ConsumerWidget {
  const ProductDetailView({super.key, required this.productId});

  final int productId;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final l10n = AppLocalizations.of(context)!;
    final state = ref.watch(productDetailProvider(productId));

    return Scaffold(
      appBar: AppBar(title: Text(l10n.productsTitle)),
      body: switch (state) {
        ProductDetailLoading() =>
          const Center(child: CircularProgressIndicator()),
        ProductDetailError() => Center(
            child: TextButton(
              onPressed:
                  ref.read(productDetailProvider(productId).notifier).load,
              child: Text(l10n.retry),
            ),
          ),
        ProductDetailSuccess(:final product) => ListView(
            padding: const EdgeInsets.all(16),
            children: [
              Image.network(product.imageUrl),
              const SizedBox(height: 12),
              Text(product.title,
                  style: Theme.of(context).textTheme.headlineSmall),
              const SizedBox(height: 24),
              FilledButton(
                onPressed: () => ref.read(cartProvider.notifier).addItem(
                      productId: product.id,
                      title: product.title,
                    ),
                child: Text(l10n.addToCart),
              ),
            ],
          ),
      },
    );
  }
}
