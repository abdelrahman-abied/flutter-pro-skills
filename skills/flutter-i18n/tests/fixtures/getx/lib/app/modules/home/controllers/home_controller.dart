import 'package:get/get.dart';

class HomeController extends GetxController {
  final message = ''.obs;

  void save() {
    message.value = 'saved'.tr;
    Get.snackbar('Saved', 'Your changes were saved');
  }
}
