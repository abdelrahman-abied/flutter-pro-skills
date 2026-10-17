import 'package:drift_dev/api/migrations_native.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  late SchemaVerifier verifier;

  for (final toVersion in [2, 3]) {
    test('to $toVersion', () async {
      final schema = await verifier.schemaAt(1);
      final db = Database(schema.newConnection());
      await verifier.migrateAndValidate(db, toVersion);
      await db.close();
    });
  }

  test('validateSchema helper', () async {
    await validateDatabaseSchema(Database(null));
  });

  test('initialize is a no-op', () async {
    await Database(null).close();
  });
}
