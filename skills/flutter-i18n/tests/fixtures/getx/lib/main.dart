import 'package:flutter/material.dart';
import 'package:get/get.dart';

import 'app/modules/home/views/home_view.dart';
import 'app/translations/app_translations.dart';

void main() => runApp(GetMaterialApp(
      translations: AppTranslations(),
      locale: const Locale('ar'),
      fallbackLocale: const Locale('en', 'US'),
      home: const HomeView(),
    ));
