import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:intl/intl.dart';

import '../../../../l10n/gen/app_localizations.dart';
import '../notifier/order_history_notifier.dart';
import '../state/order_history_state.dart';

class OrderHistoryView extends ConsumerWidget {
  const OrderHistoryView({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final l10n = AppLocalizations.of(context)!;
    final state = ref.watch(orderHistoryProvider);
    final dateFormat =
        DateFormat.yMMMd(Localizations.localeOf(context).toString());

    return Scaffold(
      appBar: AppBar(title: Text(l10n.ordersTitle)),
      body: switch (state) {
        OrderHistoryLoading() =>
          const Center(child: CircularProgressIndicator()),
        OrderHistoryError() => Center(
            child: TextButton(
              onPressed: ref.read(orderHistoryProvider.notifier).load,
              child: Text(l10n.retry),
            ),
          ),
        OrderHistorySuccess(:final orders) => ListView.builder(
            itemCount: orders.length,
            itemBuilder: (context, i) => ListTile(
              title: Text('#${orders[i].id}'),
              subtitle: Text(dateFormat.format(orders[i].placedAt)),
            ),
          ),
      },
    );
  }
}
