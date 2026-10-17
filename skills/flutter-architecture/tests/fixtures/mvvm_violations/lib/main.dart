import 'package:flutter/material.dart';
import 'package:get_it/get_it.dart';

import 'data/services/api/api_client.dart';
import 'ui/home/widgets/home_screen.dart';

void main() {
  GetIt.I.registerSingleton(ApiClient());
  runApp(const MaterialApp(home: HomeScreen()));
}
