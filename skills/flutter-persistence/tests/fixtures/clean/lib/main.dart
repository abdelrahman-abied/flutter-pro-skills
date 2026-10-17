import 'package:flutter/widgets.dart';
import 'package:provider/provider.dart';

import 'core/database/app_database.dart';

@pragma('vm:entry-point')
void backgroundSync() {
  final db = AppDatabase(openBackground());
  db.close();
}

void main() {
  final db = AppDatabase(openBackground());
  runApp(Provider<AppDatabase>(create: (_) => db, dispose: (_, d) => d.close(), child: const SizedBox()));
}

QueryExecutor openBackground() => throw UnimplementedError();
