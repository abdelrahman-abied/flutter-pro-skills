import 'package:flutter/services.dart';
import 'package:riverpod_annotation/riverpod_annotation.dart';

part 'battery_notifier.g.dart';

@riverpod
class BatteryNotifier extends _$BatteryNotifier {
  static const _channel = MethodChannel('app.example/power');

  @override
  int build() => 0;

  Future<void> refresh() async {
    final value = await _channel.invokeMethod<int>('getLevel');
    state = value ?? 0;
  }
}
