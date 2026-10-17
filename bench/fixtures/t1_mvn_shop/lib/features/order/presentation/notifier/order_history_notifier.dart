import 'package:riverpod_annotation/riverpod_annotation.dart';

import '../../domain/usecases/order_usecase.dart';
import '../state/order_history_state.dart';

part 'order_history_notifier.g.dart';

@riverpod
class OrderHistoryNotifier extends _$OrderHistoryNotifier {
  @override
  OrderHistoryState build() {
    Future.microtask(load);
    return const OrderHistoryLoading();
  }

  Future<void> load() async {
    state = const OrderHistoryLoading();
    final orders = await ref.read(fetchOrdersProvider)();
    state = OrderHistorySuccess(orders);
  }
}
