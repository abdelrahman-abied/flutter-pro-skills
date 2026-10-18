import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'src/binding.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  final binding = RealAppBinding();
  await Future.wait([binding.loadSettings(), binding.startFirebase()]);
  runApp(const ProviderScope(child: MaterialApp(home: SizedBox())));
}
