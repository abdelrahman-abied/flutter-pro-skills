import 'package:envied/envied.dart';

part 'env.g.dart';

// SEC-009: envied secret (medium) and API key (low).
@Envied(path: '.env')
abstract class Env {
  @EnviedField(varName: 'PAYMENT_CLIENT_SECRET', obfuscate: true)
  static final String paymentClientSecret = _Env.paymentClientSecret;
  @EnviedField(varName: 'MAPS_API_KEY')
  static const String mapsApiKey = _Env.mapsApiKey;
}
