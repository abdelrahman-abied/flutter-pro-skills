import 'package:firebase_messaging/firebase_messaging.dart';

void registerPushHandlers() {
  FirebaseMessaging.onBackgroundMessage((RemoteMessage message) async {
    // handled in the background isolate
  });
}
