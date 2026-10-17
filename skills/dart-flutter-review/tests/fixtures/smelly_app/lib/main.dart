import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'app/router.dart';

void main() => runApp(const ProviderScope(child: SmellyApp()));

class SmellyApp extends StatelessWidget {
  const SmellyApp({super.key});

  @override
  Widget build(BuildContext context) =>
      const MaterialApp(onGenerateRoute: buildRoute);
}
