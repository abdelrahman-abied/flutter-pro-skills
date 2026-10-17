// Configured as Pigeon's dartOut, so it is skipped even without a banner.
import 'package:flutter/services.dart';

class DeviceInfoApi {
  Future<String> model() async {
    final reply = await const BasicMessageChannel<Object?>('dev.flutter.pigeon.model', StandardMessageCodec()).send(null);
    return reply! as String;
  }
}
