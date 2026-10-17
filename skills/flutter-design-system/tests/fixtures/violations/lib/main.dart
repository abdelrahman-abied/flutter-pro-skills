import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'core/design_system/theme/app_theme.dart';
import 'features/settings/presentation/notifier/theme_mode_notifier.dart';

void main() => runApp(const ProviderScope(child: App()));

class App extends ConsumerWidget {
  const App({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return MaterialApp(
      theme: AppTheme.light,
      themeMode: ref.watch(themeModeProvider),
      home: const Placeholder(),
    );
  }
}
