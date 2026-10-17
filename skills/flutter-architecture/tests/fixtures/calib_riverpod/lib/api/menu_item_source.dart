// K3 A15: a Function-typed field is not an async method
import 'dart:async';

class MenuItem {
  const MenuItem(this.onTap);
  final FutureOr<void> Function()? onTap;
}
