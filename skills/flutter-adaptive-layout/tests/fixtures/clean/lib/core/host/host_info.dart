import 'dart:io';

import 'package:flutter/foundation.dart';

/// Web-safe: kIsWeb is checked before dart:io is touched.
bool get isDesktopHost => !kIsWeb && (Platform.isMacOS || Platform.isWindows || Platform.isLinux);

String hostName() => kIsWeb ? 'web' : Platform.operatingSystem;
