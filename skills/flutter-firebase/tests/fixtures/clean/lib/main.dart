import 'package:cloud_firestore/cloud_firestore.dart';
import 'package:firebase_app_check/firebase_app_check.dart';
import 'package:firebase_core/firebase_core.dart';
import 'package:firebase_messaging/firebase_messaging.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'core/firebase/emulators.dart';
import 'firebase_options.dart';

@pragma('vm:entry-point')
Future<void> firebaseBackgroundHandler(RemoteMessage message) async {
  await Firebase.initializeApp(options: DefaultFirebaseOptions.currentPlatform);
}

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await Firebase.initializeApp(options: DefaultFirebaseOptions.currentPlatform);
  await FirebaseAppCheck.instance.activate(
    providerAndroid: kDebugMode ? const AndroidDebugProvider() : const AndroidPlayIntegrityProvider(),
    providerApple: kDebugMode ? const AppleDebugProvider() : const AppleAppAttestProvider(),
  );
  if (kDebugMode) {
    FirebaseFirestore.instance.useFirestoreEmulator('localhost', 8080);
    await connectAuthEmulator();
  }
  if (useEmulatorsFromDefine) {
    await connectStorageLikeEmulators();
  }
  assert(() {
    FirebaseFirestore.instance.useFirestoreEmulator('10.0.2.2', 8080);
    return true;
  }());
  FirebaseMessaging.onBackgroundMessage(firebaseBackgroundHandler);
  FirebaseMessaging.onMessage.listen((message) => debugPrint(message.messageId));
  runApp(const ProviderScope(child: App()));
}

class App extends StatelessWidget {
  const App({super.key});

  @override
  Widget build(BuildContext context) => const MaterialApp(home: SizedBox());
}
