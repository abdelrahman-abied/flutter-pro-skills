import 'package:flutter_dotenv/flutter_dotenv.dart';

// SEC-008 generic: a literal credential assigned to a secret-named field.
class PaymentConfig {
  static const clientSecret = 'a8F3kQ9zLm2Xw7Pv4Tn6';
  // Not reported: storage key names and labels.
  static const accessTokenKey = 'access_token';
  static const passwordLabel = 'Password';
}

// SEC-009: a dart-define secret with a literal default, and a .env secret.
const paymentSecret = String.fromEnvironment('PAYMENT_SECRET', defaultValue: 'zX9qL2mV7tR4wK8p');
const mapsKey = String.fromEnvironment('MAPS_API_KEY');
String get apiSecret => dotenv.env['API_SECRET'] ?? '';
