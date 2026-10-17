// GUARD: ownership hand-off `_out = controller;` (undisposed-resource must
// not fire for `controller`; whoever holds `_out` disposes it).
import 'package:flutter/widgets.dart';

class SearchBinding {
  TextEditingController? _out;

  TextEditingController? get current => _out;

  void bind() {
    final controller = TextEditingController();
    _out = controller;
  }

  void release() => _out?.dispose();
}
