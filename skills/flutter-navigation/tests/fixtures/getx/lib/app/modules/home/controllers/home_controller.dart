import 'package:get/get.dart';

import '../../../routes/app_routes.dart';

class HomeController extends GetxController {
  void openHome() => Get.toNamed(Routes.HOME);

  void signOut() => Get.offAllNamed(Routes.LOGIN);

  void openLegacy() => Get.toNamed('/home');
}
