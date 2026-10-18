import 'dart:io';

import 'package:flutter/foundation.dart';

class InboxPlatformSource {
  bool get supportsBadges {
    if (kIsWeb) return false;
    return Platform.isIOS || Platform.isMacOS;
  }
}
