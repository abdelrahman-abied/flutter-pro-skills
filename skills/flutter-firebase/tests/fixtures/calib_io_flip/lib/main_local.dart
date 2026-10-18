import 'dart:async';

import 'package:firebase_core/firebase_core.dart';

import 'bootstrap.dart';

void main() async {
  await Firebase.initializeApp();
  unawaited(
    bootstrap((auth, appCheck) async {
      try {
        await auth.useAuthEmulator('localhost', 9099);
      } catch (_) {}
      return const Placeholder();
    }),
  );
}
