import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../../l10n/gen/app_localizations.dart';
import '../../domain/entities/cart_item_entity.dart';
import '../notifier/cart_notifier.dart';
import '../state/cart_state.dart';

class CartView extends ConsumerWidget {
  const CartView({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final l10n = AppLocalizations.of(context)!;
    final items = switch (ref.watch(cartProvider)) {
      CartReady(:final items) => items,
      CartError(:final items) => items,
    };

    return Scaffold(
      appBar: AppBar(title: Text(l10n.cartTitle)),
      body: items.isEmpty
          ? Center(child: Text(l10n.cartEmpty))
          : _CartList(items: items),
    );
  }
}

class _CartList extends StatelessWidget {
  const _CartList({required this.items});

  final List<CartItemEntity> items;

  @override
  Widget build(BuildContext context) {
    return ListView.builder(
      itemCount: items.length,
      itemBuilder: (context, i) => ListTile(
        title: Text(items[i].title),
        trailing: Text('${items[i].quantity}'),
      ),
    );
  }
}
