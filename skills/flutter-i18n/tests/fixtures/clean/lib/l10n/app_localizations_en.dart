// ignore: unused_import
import 'package:intl/intl.dart' as intl;
import 'app_localizations.dart';

// ignore_for_file: type=lint

/// The translations for English (`en`).
class AppLocalizationsEn extends AppLocalizations {
  AppLocalizationsEn([String locale = 'en']) : super(locale);

  @override
  String get cartTitle => 'Your cart';

  @override
  String get cartEmpty => 'Your cart is empty';

  @override
  String hello(String name) {
    return 'Hello $name';
  }

  @override
  String itemsInCart(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count items',
      one: 'One item',
      zero: 'No items',
    );
    return '$_temp0';
  }

  @override
  String totalLabel(String amount) {
    return 'Total: $amount';
  }

  @override
  String get errorNetwork => 'No connection. Try again.';
}
