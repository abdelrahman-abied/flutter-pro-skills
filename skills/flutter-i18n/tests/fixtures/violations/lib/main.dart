import 'package:flutter/material.dart';
import 'package:flutter_gen/gen_l10n/app_localizations.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'features/cart/presentation/view/cart_view.dart';

void main() => runApp(const ProviderScope(child: ShopApp()));

class ShopApp extends StatelessWidget {
  const ShopApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Shop App',
      locale: const Locale('ar'),
      home: const CartView(),
    );
  }
}
