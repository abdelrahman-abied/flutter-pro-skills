import 'package:drift/drift.dart';

const _encryptionPassword = 'drift.example.unsafe_password';

void setup(dynamic db) {
  final escapedKey = _encryptionPassword.replaceAll("'", "''");
  db.execute("pragma key = '$escapedKey'");
  db.execute('select count(*) from sqlite_master');
}

void rekey(dynamic db, String newKey) {
  db.execute("SELECT * FROM users WHERE name = '$newKey'");
}
