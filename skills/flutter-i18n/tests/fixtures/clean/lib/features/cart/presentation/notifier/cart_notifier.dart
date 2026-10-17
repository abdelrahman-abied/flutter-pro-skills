import 'package:riverpod_annotation/riverpod_annotation.dart';

import '../state/cart_state.dart';

part 'cart_notifier.g.dart';

@riverpod
class CartNotifier extends _$CartNotifier {
  @override
  CartState build() => const CartLoaded(3, 42.5);
}
