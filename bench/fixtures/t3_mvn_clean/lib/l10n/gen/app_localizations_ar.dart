// ignore: unused_import
import 'package:intl/intl.dart' as intl;
import 'app_localizations.dart';

// ignore_for_file: type=lint

/// The translations for Arabic (`ar`).
class AppLocalizationsAr extends AppLocalizations {
  AppLocalizationsAr([String locale = 'ar']) : super(locale);

  @override
  String get appTitle => 'المتجر';

  @override
  String get productsTitle => 'المنتجات';

  @override
  String get searchHint => 'ابحث عن منتج';

  @override
  String get genericError => 'حدث خطأ ما. حاول مرة أخرى.';

  @override
  String get retry => 'إعادة المحاولة';
}
