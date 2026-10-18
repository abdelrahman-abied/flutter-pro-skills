import 'package:shared_preferences/shared_preferences.dart';

class PrefsSource {
  PrefsSource(this._prefs);

  final SharedPreferences _prefs;

  String? theme() => _prefs.getString('theme_token_name');
}
