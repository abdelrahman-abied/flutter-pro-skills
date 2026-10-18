import 'package:firebase_app_check/firebase_app_check.dart';
import 'package:flutter/foundation.dart';

Future<void> activateAppCheck() async {
  await FirebaseAppCheck.instance.activate(
    providerWeb: kDebugMode ? WebDebugProvider() : ReCaptchaV3Provider('site-key-placeholder'),
    providerAndroid: const AndroidDebugProvider(),
    providerApple: const AppleDebugProvider(),
  );
}
