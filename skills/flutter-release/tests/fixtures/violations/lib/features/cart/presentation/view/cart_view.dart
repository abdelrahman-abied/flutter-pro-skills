import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';

class CartView extends StatelessWidget {
  const CartView({super.key});

  @override
  Widget build(BuildContext context) {
    if (appFlavor == 'prod') {
      return const SizedBox.shrink();
    }
    return const Text('debug cart');
  }
}
