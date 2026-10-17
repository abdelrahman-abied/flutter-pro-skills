import 'package:flutter/widgets.dart';
import 'package:riverpod_annotation/riverpod_annotation.dart';

import '../../../../l10n/app_localizations.dart';
import '../state/cart_state.dart';

part 'cart_notifier.g.dart';

@riverpod
class CartNotifier extends _$CartNotifier {
  @override
  CartState build() {
    // Builds a translated string in logic: frozen at English, ignores locale changes.
    final l10n = lookupAppLocalizations(const Locale('en'));
    return CartEmpty(l10n.cartTitle);
  }
}
