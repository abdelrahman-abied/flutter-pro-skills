import 'dart:async';

import 'package:flutter/services.dart';

class BatteryUnavailable implements Exception {
  const BatteryUnavailable(this.reason);
  final String reason;
}

class BatteryPlatformSource {
  BatteryPlatformSource({MethodChannel? channel, EventChannel? events})
      : _channel = channel ?? const MethodChannel(batteryChannel),
        _events = events ?? const EventChannel(chargingChannel);

  static const batteryChannel = 'app.example/battery';
  static const chargingChannel = 'app.example/charging';

  final MethodChannel _channel;
  final EventChannel _events;
  StreamSubscription<Object?>? _subscription;

  Future<int> level() async {
    final value = await _channel.invokeMethod<int>('getLevel');
    if (value == null || value < 0 || value > 100) {
      throw const BatteryUnavailable('bad level');
    }
    return value;
  }

  Future<String?> model() async {
    return await _channel.invokeMethod('getModel') as String?;
  }

  void watchCharging(void Function(bool) onChange) {
    _subscription = _events.receiveBroadcastStream().listen((event) => onChange(event == true));
  }

  Stream<bool> get charging => _events.receiveBroadcastStream().map((event) => event == true);

  Future<void> dispose() async {
    await _subscription?.cancel();
  }
}
