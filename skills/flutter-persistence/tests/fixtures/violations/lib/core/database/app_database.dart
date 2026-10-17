import 'package:drift/drift.dart';

part 'app_database.g.dart';

class Notes extends Table {
  IntColumn get id => integer().autoIncrement()();
  TextColumn get title => text()();
}

class MedicalRecords extends Table {
  IntColumn get id => integer().autoIncrement()();
  TextColumn get diagnosis => text()();
}

@DriftDatabase(tables: [Notes, MedicalRecords])
class AppDatabase extends _$AppDatabase {
  AppDatabase(super.e);

  @override
  int get schemaVersion => 3;
}
