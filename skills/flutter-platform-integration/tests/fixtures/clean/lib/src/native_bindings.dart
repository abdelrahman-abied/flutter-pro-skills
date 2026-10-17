import 'dart:ffi';

import 'package:ffi/ffi.dart';

Pointer<Int8> scratch() {
  final p = calloc<Int8>(8);
  return Pointer.fromAddress(p.address + 0);
}
