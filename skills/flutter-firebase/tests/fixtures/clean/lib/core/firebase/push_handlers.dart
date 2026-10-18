import 'package:firebase_messaging/firebase_messaging.dart';

class LegacyHandlers {
  static Future<void> onBackground(RemoteMessage message) async {}
}

class PushHandlers {
  @pragma('vm:entry-point')
  static Future<void> onBackground(RemoteMessage message) async {}
}
