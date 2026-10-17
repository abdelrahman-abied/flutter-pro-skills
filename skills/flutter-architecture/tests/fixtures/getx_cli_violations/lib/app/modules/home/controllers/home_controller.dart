import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:get/get.dart';

class HomeController extends GetxController {
  HomeController(this._dio);
  final Dio _dio;
  final title = ''.obs;

  Future<void> load(BuildContext context) async {
    title.value = (await _dio.get<String>('/title')).data ?? '';
    ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('loaded')));
  }
}
