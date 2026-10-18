import 'package:firebase_remote_config/firebase_remote_config.dart';

class FlagsSource {
  FlagsSource(this._remoteConfig);

  final FirebaseRemoteConfig _remoteConfig;

  String paymentKey() => _remoteConfig.getString('stripe_secret_key');

  bool canModerate() => _remoteConfig.getBool('is_admin');

  String welcome() => _remoteConfig.getString('welcome_message');
}
