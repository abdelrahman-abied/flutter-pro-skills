import 'package:shared_preferences/shared_preferences.dart';

class LocaleStore {
  const LocaleStore(this._prefs);
  final SharedPreferences _prefs;

  static const _key = 'app_locale';

  String? read() => _prefs.getString(_key);
  Future<void> write(String languageCode) => _prefs.setString(_key, languageCode);
}
