import 'package:get/get.dart';

class AppTranslations extends Translations {
  @override
  Map<String, Map<String, String>> get keys => {
        'en_US': {'greeting': 'Hello', 'saved': 'Saved'},
        'ar': {'greeting': 'مرحبًا', 'saved': 'تم الحفظ'},
      };
}
