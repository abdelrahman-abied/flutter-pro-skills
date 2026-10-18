import 'package:device_info_plus/device_info_plus.dart';
import 'package:flutter/foundation.dart';

class DeviceKind {
  static Future<bool> isTabletDevice() async {
    final info = await DeviceInfoPlugin().iosInfo;
    return info.model.toLowerCase().contains('ipad');
  }

  static bool get isPhone =>
      defaultTargetPlatform == TargetPlatform.iOS || defaultTargetPlatform == TargetPlatform.android;
}
