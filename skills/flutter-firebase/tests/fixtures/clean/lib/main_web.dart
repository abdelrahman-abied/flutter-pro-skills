import 'package:firebase_core/firebase_core.dart';
import 'package:firebase_messaging/firebase_messaging.dart';
import 'package:flutter/material.dart';

import 'core/firebase/push_handlers.dart';
import 'firebase_options.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  final initialization = Firebase.initializeApp(options: DefaultFirebaseOptions.currentPlatform);
  FirebaseMessaging.onBackgroundMessage(PushHandlers.onBackground);
  runApp(MaterialApp(
    home: FutureBuilder(
      future: initialization,
      builder: (context, snapshot) => snapshot.hasData ? const Text('ready') : const CircularProgressIndicator(),
    ),
  ));
}
