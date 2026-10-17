import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

class GeneralPreferencesNotifier extends Notifier<GeneralPrefsState> {
  @override
  GeneralPrefsState build() => const GeneralPrefsState(boardAccent: Color(0xFF629924));
}

class GeneralPrefsState {
  const GeneralPrefsState({required this.boardAccent});

  final Color boardAccent;

  static Color getFilterColor(Color surfaceColor, double meanLuminance) =>
      surfaceColor.withValues(alpha: meanLuminance < 0.5 ? 0.25 : 0.5);
}
