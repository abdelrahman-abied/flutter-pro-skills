import 'package:get/get.dart';

import '../../../widgets/custom_toast.dart';

class LoginController extends GetxController {
  LoginController(this._signIn);
  final Future<void> Function() _signIn;
  final errorMessage = ''.obs;

  Future<void> login() async {
    try {
      await _signIn();
    } catch (e) {
      // K3-E7: Get.snackbar shows the text directly, so this is UI severity (medium).
      Get.snackbar('Error', 'Login failed: ${e.toString()}');
    }
  }

  Future<void> resend() async {
    try {
      await _signIn();
    } catch (e) {
      CustomToast.errorToast('Error', 'Error because: $e');
    }
  }

  Future<void> retry() async {
    try {
      await _signIn();
    } catch (e) {
      // Stored in state: low, as before.
      errorMessage.value = e.toString();
    }
  }
}
