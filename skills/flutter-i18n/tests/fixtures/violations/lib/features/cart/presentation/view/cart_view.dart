import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:intl/intl.dart' hide TextDirection;
import 'package:intl/message_format.dart';

import '../../../../l10n/app_localizations.dart';

class CartView extends StatelessWidget {
  const CartView({super.key, this.userNote = ''});

  final String userNote;

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context)!;
    final isRtl = Directionality.of(context) == TextDirection.rtl;
    final count = 3;
    return Scaffold(
      appBar: AppBar(title: Text(l10n.cartTitle)),
      body: Column(
        children: [
          const Text('Your cart is empty'),
          const Text('OK'),
          const TextField(decoration: InputDecoration(hintText: 'Search products')),
          Padding(
            padding: const EdgeInsets.only(left: 16),
            child: Text(l10n.total + ': ' + '$count'),
          ),
          Align(alignment: Alignment.centerLeft, child: Text('${l10n.total} for all items')),
          const Icon(Icons.keyboard_arrow_right),
          Text(DateFormat.yMMMd().format(DateTime.now())),
          Text(MessageFormat('Note: $userNote').format({})),
          const Text('Ø§Ù„Ø³Ù„Ø©'),
          // --- none of these should be reported ---
          Text(l10n.hello('Sara')),
          Text('$count'),
          const Text('•'),
          const Text('home.title'),
          const Padding(padding: EdgeInsets.only(left: 8, right: 8)),
          Icon(isRtl ? Icons.keyboard_arrow_left : Icons.keyboard_arrow_right),
          if (kDebugMode) const Text('Debug build only'),
          Image.asset('assets/images/empty_cart.png'),
          Text(l10n.itemsInCart(count)),
        ],
      ),
    );
  }

  void _log() => debugPrint('Cart view rebuilt for the user');
}
