import 'dart:io';

// K3-E2: bool probes are low, not high.
Future<bool> isPortOpen(String host, int port) async {
  try {
    final s = await Socket.connect(host, port, timeout: const Duration(seconds: 1));
    s.destroy();
    return true;
  } catch (_) {
    return false;
  }
}

Future<bool> reachable(String host) async {
  try {
    await InternetAddress.lookup(host);
    return true;
  } catch (_) {
    return false;
  }
}
