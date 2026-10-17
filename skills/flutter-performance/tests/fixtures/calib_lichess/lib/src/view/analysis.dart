import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

class AnalysisService {
  final ValueNotifier<int?> currentAnalysis = ValueNotifier<int?>(null);
}

class Prefs {
  const Prefs({this.isSoundEnabled = true, this.boardTheme = 'brown'});

  final bool isSoundEnabled;
  final String boardTheme;
}

final serviceProvider = Provider((ref) => AnalysisService());
final prefsProvider = Provider((ref) => const Prefs());

// FP 4: a Notifier build() composes providers; ref.watch(x).field there is not a widget rebuild (PERF-008 must not fire).
class CurrentAnalysis extends Notifier<int?> {
  @override
  int? build() {
    final listenable = ref.watch(serviceProvider).currentAnalysis;
    return listenable.value;
  }
}

// TP 4: a ConsumerWidget rebuilds on every Prefs change to read one bool (PERF-008 still fires).
class SoundToggle extends ConsumerWidget {
  const SoundToggle({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final enabled = ref.watch(prefsProvider).isSoundEnabled;
    return Switch(value: enabled, onChanged: null);
  }
}

// TP 5: a PageController is a ScrollController; setState per page offset rebuilds the screen every frame.
class ColorPager extends StatefulWidget {
  const ColorPager({super.key});

  @override
  State<ColorPager> createState() => _ColorPagerState();
}

class _ColorPagerState extends State<ColorPager> {
  late PageController _controller;

  @override
  void initState() {
    _controller = PageController();
    _controller.addListener(() {
      setState(() {});
    });
    super.initState();
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => PageView(controller: _controller, children: const [Text('a')]);
}
