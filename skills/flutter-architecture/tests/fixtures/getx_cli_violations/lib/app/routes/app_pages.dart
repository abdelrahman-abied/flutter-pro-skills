import 'package:get/get.dart';

import '../modules/home/bindings/home_binding.dart';
import '../modules/home/views/home_view.dart';

abstract final class AppPages {
  static const initial = '/home';
  static final routes = [
    GetPage(name: initial, page: () => const HomeView(), binding: HomeBinding()),
  ];
}
