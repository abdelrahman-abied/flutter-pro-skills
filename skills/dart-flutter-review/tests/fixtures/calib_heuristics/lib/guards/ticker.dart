// K3 R5: ProviderSubscription is released with close(); ref.listen* is closed by Riverpod.
import 'dart:async';

import 'package:flutter/widgets.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

final counterProvider = StateProvider<int>((ref) => 0);

final loggerProvider = Provider<void>((ref) {
  final sub = ref.listen(counterProvider, (_, __) {});
});

class Ticker extends ConsumerStatefulWidget {
  const Ticker({super.key, required this.container, required this.stream});
  final ProviderContainer container;
  final Stream<int> stream;
  @override
  ConsumerState<Ticker> createState() => _TickerState();
}

class _TickerState extends ConsumerState<Ticker> {
  late final ProviderSubscription<int> _manual;
  late final ProviderSubscription<int> _external;
  StreamSubscription<int>? _raw;

  @override
  void initState() {
    super.initState();
    _manual = ref.listenManual(counterProvider, (_, __) {});
    _external = widget.container.listen(counterProvider, (_, __) {});
    _raw = widget.stream.listen((_) {});
  }

  @override
  void dispose() {
    _external.close();
    _raw?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => const SizedBox();
}
