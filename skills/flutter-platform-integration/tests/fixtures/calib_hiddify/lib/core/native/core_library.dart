import 'dart:ffi';
import 'dart:io';

import 'package:ffi/ffi.dart';
import 'package:path/path.dart' as p;

typedef _StartC = Int32 Function(Pointer<Utf8>, Pointer<Utf8>);
typedef _StartDart = int Function(Pointer<Utf8>, Pointer<Utf8>);

class CoreLibrary {
  static DynamicLibrary open() {
    var fullPath = '';
    if (Platform.environment.containsKey('APP_TEST')) {
      fullPath = 'core';
    }
    fullPath = p.join(fullPath, Platform.isWindows ? 'core.dll' : 'libcore.so');
    return DynamicLibrary.open(fullPath);
  }

  int start(DynamicLibrary lib, String workDir, String secret) {
    final fn = lib.lookupFunction<_StartC, _StartDart>('start');
    return fn(workDir.toNativeUtf8(), secret.toNativeUtf8());
  }
}

T withBuffer<T>(int size, T Function(Pointer<Int8>) body) {
  final memory = calloc<Int8>(size);
  try {
    return body(memory);
  } finally {
    calloc.free(memory);
  }
}
