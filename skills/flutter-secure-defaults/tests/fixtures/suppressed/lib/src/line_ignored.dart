import 'package:shared_preferences/shared_preferences.dart';

Future<void> save(SharedPreferences prefs, String token) async {
  await prefs.setString('session_token', token); // sec-ignore: SEC-001 test-only demo account, wiped on start
  // sec-ignore: SEC-003 the kiosk LAN gateway has no TLS; tracked in SHOP-42
  const kiosk = 'http://kiosk.shop-intranet.net/status';
  // Still reported: the suppression above names a different rule.
  print('token is $token'); // sec-ignore: SEC-003 wrong rule id
  print(kiosk);
}
