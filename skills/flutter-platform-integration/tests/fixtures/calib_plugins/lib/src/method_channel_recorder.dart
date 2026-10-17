import 'package:flutter/services.dart';

import 'recorder_platform.dart';

class MethodChannelRecorder extends RecorderPlatform {
  static const _channel = MethodChannel('plugins.example/recorder');

  @override
  Future<void> dispose(int id) async {
    await _channel.invokeMethod<void>('dispose', <String, Object>{'id': id});
  }

  @override
  Future<bool> purgeCache(String key) async {
    return await _channel.invokeMethod<bool>('purgeCache', key) ?? false;
  }

  Future<T> call<T>(String method, Object? args) async {
    return await _channel.invokeMethod<T>(method, args) as T;
  }

  Future<String> label() async => await _channel.invokeMethod('label') as String;

  set samplingPeriod(Duration period) {
    _channel.invokeMethod<void>('setSamplingPeriod', period.inMicroseconds);
  }
}
