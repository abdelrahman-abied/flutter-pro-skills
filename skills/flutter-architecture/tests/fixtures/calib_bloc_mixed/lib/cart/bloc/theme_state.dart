// K2 C7: a ChangeNotifier in a *_state.dart file is logic, so no ARCH-106
import 'package:flutter/foundation.dart';

class ThemeState extends ChangeNotifier {
  bool dark = false;
}
