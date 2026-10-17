import 'package:drift/drift.dart';

part 'cache_database.g.dart';

const kCacheSchemaVersion = 2;

@DriftDatabase(tables: [])
class CacheDatabase extends _$CacheDatabase {
  CacheDatabase(super.e);

  @override
  int get schemaVersion => kCacheSchemaVersion;

  @override
  MigrationStrategy get migration => MigrationStrategy(
        beforeOpen: (details) async {},
      );
}
