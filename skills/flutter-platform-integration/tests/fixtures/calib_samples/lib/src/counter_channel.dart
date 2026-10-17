import 'package:flutter/services.dart';

class Counter {
  static const methodChannel = MethodChannel('sampleCounter');

  static Future<int> increment({required int value}) async {
    final result = await methodChannel.invokeMethod<int>('increment', {'count': value});
    return result!;
  }
}
