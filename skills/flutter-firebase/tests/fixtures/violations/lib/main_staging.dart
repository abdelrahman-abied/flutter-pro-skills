import 'package:firebase_auth/firebase_auth.dart';
import 'package:firebase_core/firebase_core.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'core/messaging/push_setup.dart';
import 'firebase_options.dart';
import 'main.dart' show App;

const useEmulators = true;

Future<void> main() async {
  await Firebase.initializeApp(options: DefaultFirebaseOptions.currentPlatform);
  if (useEmulators) {
    await FirebaseAuth.instance.useAuthEmulator('localhost', 9099);
  }
  registerPushHandlers();
  runApp(const ProviderScope(child: App()));
}
