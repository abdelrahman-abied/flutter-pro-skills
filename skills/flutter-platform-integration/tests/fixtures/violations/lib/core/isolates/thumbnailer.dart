import 'dart:isolate';

import 'package:flutter/services.dart';

const _thumbs = MethodChannel('app.example/thumbs');

Future<void> renderThumbnails(List<String> ids) async {
  await Isolate.spawn(_renderEntry, ids);
}

Future<void> _renderEntry(List<String> ids) async {
  for (final id in ids) {
    await _thumbs.invokeMethod<void>('render', id);
  }
}
