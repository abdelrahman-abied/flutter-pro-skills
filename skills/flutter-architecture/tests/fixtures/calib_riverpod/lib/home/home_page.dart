// K3 A12: ref.read inside a registered listener is fine; a direct ref.read call in initState is ARCH-110
import 'package:flutter/widgets.dart';
import 'package:hooks_riverpod/hooks_riverpod.dart';

final counterProvider = NotifierProvider<Counter, int>(Counter.new);

class Counter extends Notifier<int> {
  @override
  int build() => 0;
  void set(int v) => state = v;
}

class HomePage extends ConsumerStatefulWidget {
  const HomePage({super.key});
  @override
  ConsumerState<HomePage> createState() => _HomePageState();
}

class _HomePageState extends ConsumerState<HomePage> {
  final _scroll = ScrollController();
  @override
  void initState() {
    super.initState();
    _scroll.addListener(() {
      ref.read(counterProvider.notifier).set(1);
    });
    ref.read(counterProvider.notifier).set(2);
  }

  @override
  Widget build(BuildContext context) => const SizedBox();
}
