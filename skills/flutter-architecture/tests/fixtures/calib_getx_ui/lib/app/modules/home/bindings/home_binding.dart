// K3: GetX bindings/ are the composition root
import 'package:get/get.dart';
import '../../../data/remote/home_api.dart';
import '../controllers/home_controller.dart';

class HomeBinding extends Bindings {
  @override
  void dependencies() {
    Get.lazyPut(() => HomeApi());
    Get.lazyPut(() => HomeController());
  }
}
