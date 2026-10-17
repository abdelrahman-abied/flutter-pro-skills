import 'package:flutter/foundation.dart';

/// Minimal Compass-style command: `running` blocks a second execute().
class Command1<A> extends ChangeNotifier {
  Command1(this._action);
  final Future<void> Function(A) _action;
  bool running = false;
  Future<void> execute(A arg) async {
    if (running) return;
    running = true;
    notifyListeners();
    try {
      await _action(arg);
    } finally {
      running = false;
      notifyListeners();
    }
  }
}

class CheckoutViewModel extends ChangeNotifier {
  CheckoutViewModel() {
    pay = Command1<String>(_pay);
  }
  late final Command1<String> pay;
  Future<void> _pay(String cardholder) async {}
}
