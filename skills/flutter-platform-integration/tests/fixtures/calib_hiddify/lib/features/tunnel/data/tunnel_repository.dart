import 'package:flutter/services.dart';

class TunnelRepository {
  final _channel = const MethodChannel('app.example/host');

  Future<bool> start() async {
    try {
      return await _channel.invokeMethod<bool>('start') ?? false;
    } on PlatformException {
      return false;
    }
  }
}
