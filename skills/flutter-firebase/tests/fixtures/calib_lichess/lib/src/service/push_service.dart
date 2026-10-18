import 'package:firebase_messaging/firebase_messaging.dart';

import '../binding.dart';

class PushService {
  PushService(this._binding);

  final AppBinding _binding;

  void start() {
    _binding.setBackgroundHandler(_onBackground);
    FirebaseMessaging.onBackgroundMessage(_legacyHandler);
  }

  @pragma('vm:entry-point')
  static Future<void> _onBackground(RemoteMessage message) async {}

  static Future<void> _legacyHandler(RemoteMessage message) async {}
}
