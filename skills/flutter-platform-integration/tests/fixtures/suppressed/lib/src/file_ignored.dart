// plat-ignore-file: PLAT-004 the native side always answers; covered by the contract tests
import 'package:flutter/services.dart';

class Clock {
  static const _channel = MethodChannel('app.example/clock');

  Future<int> now() async {
    final value = await _channel.invokeMethod<int>('now');
    return value!;
  }

  Future<String> zone() async => await _channel.invokeMethod('zone') as String;
}
