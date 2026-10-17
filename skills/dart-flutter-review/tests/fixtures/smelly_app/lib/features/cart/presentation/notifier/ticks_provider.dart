// GUARD: tear-off release `ref.onDispose(sub.cancel)` /
// `ref.onDispose(controller.close)` (undisposed-resource must not fire).
import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';

final ticker = Stream<int>.periodic(const Duration(seconds: 1), (i) => i);

final ticksProvider = StreamProvider<int>((ref) {
  final controller = StreamController<int>();
  final sub = ticker.listen(controller.add);
  ref.onDispose(sub.cancel);
  ref.onDispose(controller.close);
  return controller.stream;
});
