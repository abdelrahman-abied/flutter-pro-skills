import 'package:firebase_remote_config/firebase_remote_config.dart';

class FlagsSource {
  FlagsSource(this._remoteConfig);

  final FirebaseRemoteConfig _remoteConfig;

  Future<void> init() => _remoteConfig.setDefaults(const {'welcome_message': 'Hi', 'new_checkout_enabled': false});

  String welcome() => _remoteConfig.getString('welcome_message');

  bool newCheckout() => _remoteConfig.getBool('new_checkout_enabled');
}
