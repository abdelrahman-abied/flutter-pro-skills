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
  String get loginTitle => 'تسجيل الدخول';

  @override
  String get emailLabel => 'البريد الإلكتروني';

  @override
  String get passwordLabel => 'كلمة المرور';

  @override
  String get loginButton => 'دخول';

  @override
  String get productsTitle => 'المنتجات';

  @override
  String get searchHint => 'ابحث عن منتج';

  @override
  String get addToCart => 'أضف إلى السلة';

  @override
  String get cartTitle => 'السلة';

  @override
  String get cartEmpty => 'سلتك فارغة';

  @override
  String get ordersTitle => 'الطلبات';

  @override
  String get profileTitle => 'الملف الشخصي';

  @override
  String get saveButton => 'حفظ';

  @override
  String get nameLabel => 'الاسم';

  @override
  String versionLabel(String version) {
    return 'الإصدار $version';
  }

  @override
  String get genericError => 'حدث خطأ ما. حاول مرة أخرى.';

  @override
  String get retry => 'إعادة المحاولة';

  @override
  String get invalidEmail => 'أدخل بريدًا إلكترونيًا صحيحًا';

  @override
  String get passwordRequired => 'أدخل كلمة المرور';
}
