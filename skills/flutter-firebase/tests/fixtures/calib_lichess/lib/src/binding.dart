import 'package:firebase_core/firebase_core.dart';
import 'package:firebase_messaging/firebase_messaging.dart';

abstract class AppBinding {
  Future<void> startFirebase();
  void setBackgroundHandler(BackgroundMessageHandler handler);
}

class RealAppBinding implements AppBinding {
  Future<void> loadSettings() async {}

  @override
  Future<void> startFirebase() async {
    await Firebase.initializeApp();
  }

  @override
  void setBackgroundHandler(BackgroundMessageHandler handler) {
    FirebaseMessaging.onBackgroundMessage(handler);
  }
}
