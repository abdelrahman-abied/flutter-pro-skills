import 'package:get_it/get_it.dart';
import 'package:riverpod_annotation/riverpod_annotation.dart';

import '../database/app_database.dart';

part 'database_providers.g.dart';

@riverpod
AppDatabase appDatabase(Ref ref) {
  final db = AppDatabase(openConnection());
  ref.onDispose(db.close);
  return db;
}

void registerDatabases(GetIt getIt) {
  getIt.registerFactory<AppDatabase>(() => AppDatabase(openConnection()));
}

QueryExecutor openConnection() => throw UnimplementedError();
