import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'src/messages.dart';

void main() {
  final deviceInfo = DeviceInfoApi();
  runApp(ProviderScope(child: MaterialApp(home: Text('$deviceInfo'))));
}
