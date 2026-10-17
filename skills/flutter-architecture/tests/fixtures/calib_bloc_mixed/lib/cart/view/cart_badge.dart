// K2 FN-2: a get_it alias used in the UI -> ARCH-104
import 'package:flutter/widgets.dart';
import 'package:calib_bloc_mixed/injector.dart';
import 'package:calib_bloc_mixed/shopping_repository.dart';

class CartBadge extends StatelessWidget {
  const CartBadge({super.key});
  @override
  Widget build(BuildContext context) {
    injector<ShoppingRepository>().loadCatalog();
    return const SizedBox();
  }
}
