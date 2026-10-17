// K3 R6: `future:` is only a smell on a FutureBuilder/StreamBuilder inside build().
// K3 R7: a UniqueKey State field is one stable key per State.
// K3 R8: flutter_animate's `.then(delay: ...)` is not Future.then.
import 'package:flutter/material.dart';

Future<int> load() async => 1;

class Loader extends StatefulWidget {
  const Loader({super.key});
  @override
  State<Loader> createState() => _LoaderState();
}

class _LoaderState extends State<Loader> {
  final _key = UniqueKey();
  late final Future<int> _future = load();
  Future<int>? _cached;

  void _retry() {
    showRetry(future: load());
  }

  @override
  Widget build(BuildContext context) {
    return Column(
      key: _key,
      children: [
        FutureBuilder<int>(future: _future, builder: (c, s) => Text('${s.data}')),
        FutureBuilder<int>(future: _cached ??= load(), builder: (c, s) => const SizedBox()),
        const Text('hi').animate().fadeIn().then(delay: 200.ms).slide(),
      ],
    );
  }
}

void showRetry({required Future<int> future}) {}
