import 'package:local_auth/local_auth.dart';

class BiometricService {
  final _auth = LocalAuthentication();

  // K1-E3: a capability probe (bool, catch -> false) is low, not high.
  Future<bool> isAvailable() async {
    try {
      return await _auth.isDeviceSupported();
    } catch (e) {
      return false;
    }
  }

  // Still high: not a probe, and the default hides the failure.
  Future<int> enrolledCount() async {
    try {
      final list = await _auth.getAvailableBiometrics();
      return list.length;
    } catch (e) {
      return 0;
    }
  }
}
