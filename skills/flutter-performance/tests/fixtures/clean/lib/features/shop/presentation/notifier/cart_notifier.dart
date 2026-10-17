import 'package:flutter_riverpod/flutter_riverpod.dart';

class CartState {
  const CartState({this.items = const [], this.total = 0, this.title = ''});

  final List<String> items;
  final int total;
  final String title;
}

final settingsProvider = Provider<CartState>((ref) => const CartState());

class CartNotifier extends Notifier<CartState> {
  @override
  CartState build() {
    // Watching a whole object in a provider build is how providers compose.
    final title = ref.watch(settingsProvider).title;
    final sorted = [...ref.watch(settingsProvider).items]..sort();
    return CartState(items: sorted, title: title);
  }
}

final cartProvider = NotifierProvider<CartNotifier, CartState>(CartNotifier.new);
final ordersProvider = FutureProvider<List<String>>((ref) async => const []);
