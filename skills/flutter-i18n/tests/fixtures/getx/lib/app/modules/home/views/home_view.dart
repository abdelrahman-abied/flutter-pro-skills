import 'package:flutter/material.dart';
import 'package:get/get.dart';

import '../controllers/home_controller.dart';

class HomeView extends GetView<HomeController> {
  const HomeView({super.key});

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        Text('greeting'.tr),
        Obx(() => Text(controller.message.value)),
        const Padding(padding: EdgeInsets.only(right: 12)),
      ],
    );
  }
}
