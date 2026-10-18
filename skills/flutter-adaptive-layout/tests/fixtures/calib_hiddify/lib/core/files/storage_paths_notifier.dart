import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:riverpod_annotation/riverpod_annotation.dart';

import '../util/host.dart';

part 'storage_paths_notifier.g.dart';

@Riverpod(keepAlive: true)
class StoragePaths extends _$StoragePaths {
  @override
  Future<String> build() async {
    if (kIsWeb) return '.';
    if (Host.runsOnWindows || Host.runsOnLinux) {
      return besideExecutable().path;
    }
    return '/data';
  }

  static Directory besideExecutable() {
    final exe = File(Platform.resolvedExecutable);
    return Directory('${exe.parent.path}/data');
  }
}
