import 'package:hive/hive.dart';

class HealthLocalSource {
  HealthLocalSource(this._key);

  final List<int> _key;
  Box<String>? _box;

  Future<Box<String>> records() async =>
      _box ??= await Hive.openBox<String>('medical_records', encryptionCipher: HiveAesCipher(_key));

  Future<Box<String>> settings() => Hive.openBox<String>('settings');

  Future<void> cacheAll(Box<String> box, Map<String, String> items) async {
    for (final e in items.entries) {
      await box.put(e.key, e.value);
    }
  }
}
