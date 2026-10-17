import 'package:flutter/material.dart';
import 'package:get/get.dart';

import 'home_controller.dart';

class HomeView extends StatelessWidget {
  const HomeView({super.key});

  @override
  Widget build(BuildContext context) {
    final c = Get.put(HomeController());
    final again = Get.find<HomeController>(); // ARCH-104 is not reported under getx
    return Obx(() => Text('${c.title.value} ${again.title}'));
  }
}
