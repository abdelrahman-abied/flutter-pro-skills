import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:intl/intl.dart';

import '../../../../l10n/app_localizations.dart';
import '../notifier/cart_notifier.dart';
import '../state/cart_state.dart';

class CartView extends ConsumerWidget {
  const CartView({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final l10n = AppLocalizations.of(context);
    final locale = Localizations.localeOf(context).toString();
    final state = ref.watch(cartNotifierProvider);
    return Scaffold(
      appBar: AppBar(title: Text(l10n.cartTitle)),
      body: switch (state) {
        CartLoaded(:final count, :final total) => Column(
            children: [
              Padding(
                padding: const EdgeInsetsDirectional.only(start: 16),
                child: Text(l10n.itemsInCart(count)),
              ),
              Align(
                alignment: AlignmentDirectional.centerStart,
                child: Text(l10n.totalLabel(
                  NumberFormat.currency(locale: locale, name: 'SAR').format(total),
                )),
              ),
              Text(DateFormat.yMMMd(locale).format(DateTime.now())),
              const Icon(Icons.chevron_right),
              const Text('•'),
              Text('$count'),
            ],
          ),
        CartError(:final failure) => Text(switch (failure) {
            CartFailure.network => l10n.errorNetwork,
            CartFailure.unknown => l10n.cartEmpty,
          }),
      },
    );
  }
}
