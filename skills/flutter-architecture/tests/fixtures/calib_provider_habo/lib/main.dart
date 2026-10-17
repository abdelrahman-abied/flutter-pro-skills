// K1 A4: bootstrap I/O in main() is fine even though the file also declares a widget
import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  final prefs = await SharedPreferences.getInstance();
  final cfg = jsonDecode(prefs.getString('cfg') ?? '{}');
  runApp(App(config: cfg as Map<String, dynamic>));
}

class App extends StatelessWidget {
  const App({super.key, required this.config});
  final Map<String, dynamic> config;
  @override
  Widget build(BuildContext context) => const MaterialApp();
}
