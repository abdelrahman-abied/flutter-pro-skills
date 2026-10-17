import 'dart:ffi';

import 'package:ffi/ffi.dart';

typedef _ParseC = Int32 Function(Pointer<Utf8>, Pointer<Pointer<Utf8>>, Int32);
typedef _ParseDart = int Function(Pointer<Utf8>, Pointer<Pointer<Utf8>>, int);
typedef _TrackC = Void Function(Pointer<Void>, Pointer<Void>);
typedef _TrackDart = void Function(Pointer<Void>, Pointer<Void>);

Pointer<Pointer<Utf8>> toNativeArgs(List<String> args) {
  final array = calloc<Pointer<Utf8>>(args.length);
  for (var i = 0; i < args.length; i++) {
    array[i] = args[i].toNativeUtf8();
  }
  return array;
}

int parseHeader(DynamicLibrary lib, String path, List<String> args) {
  final parse = lib.lookupFunction<_ParseC, _ParseDart>('parse');
  final nativeArgs = toNativeArgs(args);
  return parse(path.toNativeUtf8().cast(), nativeArgs, args.length);
}

class TrackedRef {
  TrackedRef._(this.flag, this.trace);

  final Pointer<Bool> flag;
  final Pointer<Pointer<Char>> trace;

  factory TrackedRef.create(DynamicLibrary lib, Object owner) {
    final track = lib.lookupFunction<_TrackC, _TrackDart>('track');
    final flag = calloc<Bool>();
    var trace = nullptr.cast<Pointer<Char>>();
    assert(() {
      trace = calloc<Pointer<Char>>();
      newFinalizableHandle(owner, trace.cast());
      return true;
    }());
    track(flag.cast(), trace.cast());
    return TrackedRef._(flag, trace);
  }
}

void newFinalizableHandle(Object owner, Pointer<Void> pointer) {}
