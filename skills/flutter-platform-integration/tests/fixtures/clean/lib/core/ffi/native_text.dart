import 'dart:ffi';
import 'dart:io';

import 'package:ffi/ffi.dart';

typedef _MeasureC = Int32 Function(Pointer<Utf8>);
typedef _MeasureDart = int Function(Pointer<Utf8>);

final class NativeBuffer implements Finalizable {
  NativeBuffer(int length) : pointer = calloc<Int32>(length) {
    _finalizer.attach(this, pointer.cast(), detach: this);
  }

  static final _finalizer = NativeFinalizer(calloc.nativeFree);
  final Pointer<Int32> pointer;
}

String _libName() => Platform.isAndroid ? 'libtext.so' : 'text.framework/text';

class NativeText {
  NativeText() : _lib = DynamicLibrary.open(_libName());

  final DynamicLibrary _lib;
  static final _process = DynamicLibrary.process();

  late final _measure = _lib.lookupFunction<_MeasureC, _MeasureDart>('measure');

  int measure(String text) {
    final pointer = text.toNativeUtf8();
    try {
      return _measure(pointer);
    } finally {
      malloc.free(pointer);
    }
  }

  int measureArena(String text) => using((arena) => _measure(text.toNativeUtf8(allocator: arena)));

  Pointer<Int32> buffer(int length) {
    final data = calloc<Int32>(length);
    data[0] = length;
    return data;
  }

  int sum(List<int> values) {
    final data = calloc<Int32>(values.length);
    try {
      for (var i = 0; i < values.length; i++) {
        data[i] = values[i];
      }
      return values.length;
    } finally {
      calloc.free(data);
    }
  }

  Pointer<Pointer<Utf8>> strings(List<String> values) {
    final array = calloc<Pointer<Utf8>>(values.length);
    for (var i = 0; i < values.length; i++) {
      array[i] = values[i].toNativeUtf8();
    }
    return array;
  }

  bool get hasProcess => _process.providesSymbol('main');
}

DynamicLibrary openBundled() => DynamicLibrary.open('libtext.so');
