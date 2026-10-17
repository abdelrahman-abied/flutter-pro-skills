import 'package:riverpod_annotation/riverpod_annotation.dart';

import '../state/order_state.dart';

part 'orders_notifier.g.dart';

@riverpod
class OrdersNotifier extends _$OrdersNotifier {
  @override
  OrderState build() => throw UnimplementedError();
}
