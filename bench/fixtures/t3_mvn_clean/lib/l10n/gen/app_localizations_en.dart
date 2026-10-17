// ignore: unused_import
import 'package:intl/intl.dart' as intl;
import 'app_localizations.dart';

// ignore_for_file: type=lint

/// The translations for English (`en`).
class AppLocalizationsEn extends AppLocalizations {
  AppLocalizationsEn([String locale = 'en']) : super(locale);

  @override
  String get appTitle => 'Shop';

  @override
  String get productsTitle => 'Products';

  @override
  String get searchHint => 'Search products';

  @override
  String get genericError => 'Something went wrong. Please try again.';

  @override
  String get retry => 'Retry';
}
