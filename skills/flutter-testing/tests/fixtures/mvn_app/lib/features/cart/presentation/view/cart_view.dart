import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../notifier/cart_notifier.dart';
import '../widget/cart_badge.dart';

class CartView extends ConsumerWidget {
  const CartView({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final total = ref.watch(cartNotifierProvider);
    return Scaffold(
      appBar: AppBar(actions: [CartBadge(count: total.valueOrNull ?? 0)]),
      body: switch (total) {
        AsyncData(:final value) => Text('Total: $value'),
        AsyncError() => const Text('Could not load the cart'),
        _ => const CircularProgressIndicator(),
      },
    );
  }
}
