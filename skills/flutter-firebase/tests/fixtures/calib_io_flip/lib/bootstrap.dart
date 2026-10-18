import 'dart:async';

import 'package:firebase_app_check/firebase_app_check.dart';
import 'package:firebase_auth/firebase_auth.dart';
import 'package:flutter/widgets.dart';

typedef AppBuilder = FutureOr<Widget> Function(FirebaseAuth auth, FirebaseAppCheck appCheck);

Future<void> bootstrap(AppBuilder builder) async {
  WidgetsFlutterBinding.ensureInitialized();
  await FirebaseAppCheck.instance.activate(webProvider: ReCaptchaV3Provider('site-key-placeholder'));
  runApp(await builder(FirebaseAuth.instance, FirebaseAppCheck.instance));
}
