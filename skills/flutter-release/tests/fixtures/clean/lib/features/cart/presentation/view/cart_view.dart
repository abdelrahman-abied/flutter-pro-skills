import 'package:flutter/widgets.dart';

class CartView extends StatelessWidget {
  const CartView({super.key, required this.showBeta});

  final bool showBeta;

  @override
  Widget build(BuildContext context) => showBeta ? const Text('beta') : const SizedBox.shrink();
}
