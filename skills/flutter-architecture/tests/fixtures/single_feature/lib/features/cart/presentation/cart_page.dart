import 'package:flutter/material.dart';

class CartPage extends StatefulWidget {
  const CartPage({super.key});

  @override
  State<CartPage> createState() => _CartPageState();
}

class _CartPageState extends State<CartPage> {
  int _count = 0;

  @override
  Widget build(BuildContext context) =>
      TextButton(onPressed: () => setState(() => _count++), child: Text('$_count'));
}
