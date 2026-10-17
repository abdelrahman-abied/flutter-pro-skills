import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../notifier/settings_notifier.dart';
import '../state/settings_state.dart';

/// A field the user types into: the TextEditingController is ephemeral UI
/// state, so it lives (and is disposed) here, not in the notifier.
class SettingsView extends ConsumerStatefulWidget {
  const SettingsView({super.key});

  @override
  ConsumerState<SettingsView> createState() => _SettingsViewState();
}

class _SettingsViewState extends ConsumerState<SettingsView> {
  final _nickname = TextEditingController();
  static int _builds = 0; // a State's own static counter is not global app state

  @override
  void dispose() {
    _nickname.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    _builds++;
    final state = ref.watch(settingsNotifierProvider);
    return switch (state) {
      AsyncData(value: SettingsSuccess(:final settings)) => TextField(
          controller: _nickname..text = settings.nickname,
          onSubmitted: ref.read(settingsNotifierProvider.notifier).rename,
        ),
      AsyncError(:final error) => Text('$error'),
      _ => const CircularProgressIndicator(),
    };
  }
}
