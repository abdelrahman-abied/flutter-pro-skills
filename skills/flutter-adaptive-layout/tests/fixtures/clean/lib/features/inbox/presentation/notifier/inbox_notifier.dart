import 'dart:io';

import 'package:flutter/foundation.dart';

import '../../../../core/host/host_info.dart';

class InboxNotifier extends ChangeNotifier {
  String? selectedId;
  bool get compactBadges => !kIsWeb && Platform.isAndroid;
  bool get trayIcon => isDesktopHost && Platform.isMacOS;

  void select(String id) {
    selectedId = id;
    notifyListeners();
  }
}

class BreakpointNotifier extends ChangeNotifier {
  Size? last;
}
