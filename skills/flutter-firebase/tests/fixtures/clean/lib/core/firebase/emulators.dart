import 'package:firebase_auth/firebase_auth.dart';
import 'package:firebase_database/firebase_database.dart';
import 'package:flutter/foundation.dart';

const useEmulatorsFromDefine = bool.fromEnvironment('USE_EMULATORS');

Future<void> connectAuthEmulator() async {
  await FirebaseAuth.instance.useAuthEmulator('localhost', 9099);
}

Future<void> connectStorageLikeEmulators() async {
  if (kReleaseMode) return;
  FirebaseDatabase.instance.useDatabaseEmulator('localhost', 9000);
}
