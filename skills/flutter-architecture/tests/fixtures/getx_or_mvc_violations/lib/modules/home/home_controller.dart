import 'package:flutter/material.dart';
import 'package:get/get.dart';

import '../cart/cart_controller.dart';

class HomeController extends GetxController {
  final title = 'Home'.obs;
  final accent = Colors.blue;

  void open() => Get.find<CartController>().count.value++;
}
