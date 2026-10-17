import 'dart:ffi';

import 'package:ffi/ffi.dart';
import 'package:path_provider/path_provider.dart';

typedef _MeasureC = Int32 Function(Pointer<Utf8>);
typedef _MeasureDart = int Function(Pointer<Utf8>);

class NativeText {
  NativeText(this._lib);

  final DynamicLibrary _lib;

  late final _measure = _lib.lookupFunction<_MeasureC, _MeasureDart>('measure');

  int measure(String text) {
    final pointer = text.toNativeUtf8();
    return _measure(pointer);
  }

  int measureInline(String text) => _measure(text.toNativeUtf8());

  Pointer<Int32> buffer(int length) {
    final data = calloc<Int32>(length);
    data[0] = length;
    _measure(data.cast());
    return nullptr;
  }
}

Future<DynamicLibrary> loadPlugin(String name) async {
  final dir = await getApplicationSupportDirectory();
  final path = '${dir.path}/plugins/lib$name.so';
  return DynamicLibrary.open(path);
}
