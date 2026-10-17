import 'package:get_it/get_it.dart';

import '../database/app_database.dart';

void configure(GetIt getIt, QueryExecutor e) {
  getIt.registerLazySingleton<AppDatabase>(() => AppDatabase(e), dispose: (db) => db.close());
}
