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
  String get loginTitle => 'Sign in';

  @override
  String get emailLabel => 'Email';

  @override
  String get passwordLabel => 'Password';

  @override
  String get loginButton => 'Sign in';

  @override
  String get productsTitle => 'Products';

  @override
  String get searchHint => 'Search products';

  @override
  String get addToCart => 'Add to cart';

  @override
  String get cartTitle => 'Cart';

  @override
  String get cartEmpty => 'Your cart is empty';

  @override
  String get ordersTitle => 'Orders';

  @override
  String get profileTitle => 'Profile';

  @override
  String get saveButton => 'Save';

  @override
  String get nameLabel => 'Name';

  @override
  String versionLabel(String version) {
    return 'Version $version';
  }

  @override
  String get genericError => 'Something went wrong. Please try again.';

  @override
  String get retry => 'Retry';

  @override
  String get invalidEmail => 'Enter a valid email address';

  @override
  String get passwordRequired => 'Enter your password';
}
