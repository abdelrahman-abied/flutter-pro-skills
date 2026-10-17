import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:logging/logging.dart';
import 'package:riverpod_annotation/riverpod_annotation.dart';

part 'home_screen.g.dart';

final _logger = Logger('Home');
final loggy = _logger;
void dPrint(String Function() message) {}

@riverpod
class Counter extends _$Counter {
  @override
  int build() => 0;

  String describe(Object error) => 'Counter failed: $error';
}

class HomeScreen extends ConsumerWidget {
  const HomeScreen({super.key});

  Future<void> _save(BuildContext context, Future<void> Function() save) async {
    try {
      await save();
    } catch (e, st) {
      // K3-E3: logging is not display.
      loggy.severe('save failed: $e', e, st);
      dPrint(() => 'save failed: $e');
      // K3-E3: a comparison is not display.
      if (e.toString() == 'cancelled') return;
      if (!context.mounted) return;
      // True positive: raw text in a snackbar, inside a widget class (medium, even though the file declares a notifier).
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('Could not save: $e')));
    }
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final ids = [1, 2, 3];
    // K3-E3: `e` here is a list element, not the catch variable above.
    final labels = ids.map((e) => e.toString()).toList();
    return Column(children: [
      for (final l in labels) Text(l),
      TextButton(onPressed: () => _save(context, () async {}), child: const Text('save')),
    ]);
  }
}
