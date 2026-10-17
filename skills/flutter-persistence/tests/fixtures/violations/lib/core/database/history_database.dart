import 'package:drift/drift.dart';

part 'history_database.g.dart';

@DriftDatabase(tables: [])
class HistoryDatabase extends _$HistoryDatabase {
  HistoryDatabase(super.e);

  @override
  int get schemaVersion => 4;

  @override
  MigrationStrategy get migration {
    return MigrationStrategy(
      onUpgrade: (m, from, to) async {
        await customStatement('PRAGMA user_version = $to');
      },
    );
  }
}
