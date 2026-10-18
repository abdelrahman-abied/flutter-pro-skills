import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'app_state.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  runApp(ChangeNotifierProvider(create: (_) => ApplicationState(), child: const MaterialApp(home: SizedBox())));
}
