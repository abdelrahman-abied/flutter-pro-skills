import 'dart:ui';

import 'package:flutter/material.dart';

void main() {
  FlutterError.onError = FlutterError.presentError;
  PlatformDispatcher.instance.onError = (error, stack) => true;
  runApp(const MaterialApp(home: SizedBox()));
}
