// ignore: unused_import
import 'package:intl/intl.dart' as intl;
import 'app_localizations.dart';

// ignore_for_file: type=lint

/// The translations for Arabic (`ar`).
class AppLocalizationsAr extends AppLocalizations {
  AppLocalizationsAr([String locale = 'ar']) : super(locale);

  @override
  String get cartTitle => 'سلة التسوق';

  @override
  String get cartEmpty => 'سلتك فارغة';

  @override
  String hello(String name) {
    return 'مرحبًا $name';
  }

  @override
  String itemsInCart(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count عنصر',
      many: '$count عنصرًا',
      few: '$count عناصر',
      two: 'عنصران',
      one: 'عنصر واحد',
      zero: 'لا توجد عناصر',
    );
    return '$_temp0';
  }

  @override
  String totalLabel(String amount) {
    return 'الإجمالي: $amount';
  }

  @override
  String get errorNetwork => 'لا يوجد اتصال. حاول مرة أخرى.';
}
