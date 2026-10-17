import 'package:flutter/material.dart';

import '../repositories/cart_repository.dart';

class CartScreen extends StatelessWidget {
  const CartScreen({super.key, this.repository});
  final CartRepository? repository;

  @override
  Widget build(BuildContext context) => FutureBuilder<List<String>>(
        future: repository?.items(),
        builder: (context, snap) => Text('${snap.data}'),
      );
}
