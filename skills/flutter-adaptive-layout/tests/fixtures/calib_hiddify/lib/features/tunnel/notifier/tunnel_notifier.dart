import 'dart:io';

import 'package:riverpod_annotation/riverpod_annotation.dart';

part 'tunnel_notifier.g.dart';

@Riverpod(keepAlive: true)
class TunnelNotifier extends _$TunnelNotifier {
  @override
  Stream<bool> build() async* {
    if (Platform.isIOS) {
      await _prepare();
    }
    yield false;
  }

  Future<void> _prepare() async {}
}
