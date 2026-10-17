import 'package:flutter/services.dart';

class BatteryPlatformSource {
  static const _channel = MethodChannel('app.example/battery');

  Future<int> level() async {
    final value = await _channel.invokeMethod<int>('getLevel');
    return value!;
  }

  Future<String> model() async {
    return await _channel.invokeMethod('getModel') as String;
  }
}
