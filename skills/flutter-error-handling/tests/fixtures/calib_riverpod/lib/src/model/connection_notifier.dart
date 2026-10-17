import 'package:flutter_riverpod/flutter_riverpod.dart';

class ConnectionNotifier extends Notifier<bool> {
  final _call = SingleCall();

  @override
  bool build() => false;

  Future<void> toggle(Future<bool> Function() connect) async {
    state = await _call.run(connect, onIgnored: state);
  }
}

// K3-E5 (hiddify): the flag is reset in `finally`, so the caller never stays "running".
class SingleCall {
  bool _running = false;

  Future<T> run<T>(Future<T> Function() task, {required T onIgnored}) async {
    if (_running) return onIgnored;
    _running = true;
    try {
      return await task();
    } finally {
      _running = false;
    }
  }
}
