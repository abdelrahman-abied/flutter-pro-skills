import 'package:flutter/material.dart';

class CartBadge extends StatelessWidget {
  final int count;
  const CartBadge({required this.count, super.key});

  @override
  Widget build(BuildContext context) =>
      count == 0 ? const SizedBox.shrink() : Badge(label: Text('$count'));
}
