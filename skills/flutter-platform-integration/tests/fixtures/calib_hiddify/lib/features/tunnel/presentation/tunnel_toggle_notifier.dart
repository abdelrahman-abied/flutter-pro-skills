import 'package:flutter/services.dart';
import 'package:riverpod_annotation/riverpod_annotation.dart';

part 'tunnel_toggle_notifier.g.dart';

@riverpod
class TunnelToggleNotifier extends _$TunnelToggleNotifier {
  static const _control = MethodChannel('app.example/tunnel-control');

  @override
  bool build() => false;

  Future<void> toggle() async {
    try {
      await _control.invokeMethod<void>('toggle');
      state = !state;
    } on PlatformException {
      state = false;
    }
  }
}
