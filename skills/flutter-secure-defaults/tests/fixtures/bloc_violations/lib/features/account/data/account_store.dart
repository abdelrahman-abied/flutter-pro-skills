import 'package:get_storage/get_storage.dart';
import 'package:sqflite/sqflite.dart';

// SEC-001: GetStorage (plain JSON file) and a sqflite password column.
class AccountStore {
  AccountStore(this._db);

  final Database _db;
  final _box = GetStorage();

  Future<void> remember(String user, String password, String refreshToken) async {
    await _box.write('refreshToken', refreshToken);
    await _db.insert('accounts', {'user': user, 'password': password});
  }
}
