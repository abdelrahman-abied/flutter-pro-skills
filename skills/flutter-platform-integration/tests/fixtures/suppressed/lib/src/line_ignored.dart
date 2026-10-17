import 'dart:ffi';

import 'package:ffi/ffi.dart';

void keepForever(void Function(Pointer<Utf8>) register) {
  // plat-ignore: PLAT-006 the native registry owns this string and frees it on shutdown
  register('app'.toNativeUtf8());
  register('other'.toNativeUtf8());
}
