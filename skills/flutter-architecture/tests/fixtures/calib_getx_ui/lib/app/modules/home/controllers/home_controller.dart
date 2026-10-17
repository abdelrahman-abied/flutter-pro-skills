// K3 A11: material only for Colors/TextEditingController is idiomatic in GetX -> no ARCH-009
import 'package:flutter/material.dart';
import 'package:get/get.dart';

class HomeController extends GetxController {
  final accent = Colors.blue;
  final name = TextEditingController();
}
