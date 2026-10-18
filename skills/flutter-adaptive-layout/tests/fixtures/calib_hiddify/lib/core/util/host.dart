import 'dart:io';

import 'package:flutter/foundation.dart';

abstract final class Host {
  static bool get runsOnWindows => !kIsWeb && Platform.isWindows;
  static bool get runsOnLinux => !kIsWeb && Platform.isLinux;
}
