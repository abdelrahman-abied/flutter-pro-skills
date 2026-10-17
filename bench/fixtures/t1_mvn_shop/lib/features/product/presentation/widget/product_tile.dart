import 'package:flutter/material.dart';
import 'package:intl/intl.dart';

import '../../domain/entities/product_entity.dart';

class ProductTile extends StatelessWidget {
  const ProductTile({super.key, required this.product, required this.onTap});

  final ProductEntity product;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final price = NumberFormat.simpleCurrency(
      locale: Localizations.localeOf(context).toString(),
    ).format(product.priceCents / 100);
    return ListTile(
      leading: Image.network(product.imageUrl, width: 48, height: 48),
      title: Text(product.title),
      subtitle: Text(price),
      onTap: onTap,
    );
  }
}
