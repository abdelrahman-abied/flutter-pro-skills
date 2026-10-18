import 'dart:ui' as ui;

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:window_manager/window_manager.dart';

import 'core/host/host_info.dart';
import 'features/inbox/presentation/view/inbox_view.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  if (isDesktopHost) {
    await windowManager.ensureInitialized();
    await windowManager.setMinimumSize(const Size(400, 600));
  }
  final view = ui.PlatformDispatcher.instance.views.first;
  if (view.physicalSize.shortestSide / view.devicePixelRatio < 600) {
    // small phones only: tablets, foldables and desktop windows keep every orientation
    await SystemChrome.setPreferredOrientations([DeviceOrientation.portraitUp]);
  }
  if (!kIsWeb) {
    debugPrint('host: ${hostName()}');
  }
  runApp(const MaterialApp(home: InboxView()));
}
