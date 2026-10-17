import 'dart:isolate';

import 'package:flutter/services.dart';

const _thumbs = MethodChannel('app.example/thumbs');

Future<void> renderThumbnails(List<String> ids) async {
  final token = RootIsolateToken.instance!;
  await Isolate.spawn(_renderEntry, (token, ids));
}

Future<void> _renderEntry((RootIsolateToken, List<String>) args) async {
  BackgroundIsolateBinaryMessenger.ensureInitialized(args.$1);
  for (final id in args.$2) {
    try {
      await _thumbs.invokeMethod<void>('render', id);
    } on PlatformException {
      continue;
    }
  }
}

Future<int> countWords(String text) => Isolate.run(() => text.split(' ').length);
