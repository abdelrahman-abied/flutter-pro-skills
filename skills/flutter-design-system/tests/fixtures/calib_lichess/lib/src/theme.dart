import 'package:flutter/material.dart';

import 'styles/styles.dart';

ThemeData makeAppTheme(Brightness brightness) {
  final theme = ThemeData.from(colorScheme: ColorScheme.fromSeed(seedColor: Colors.teal, brightness: brightness));
  return theme.copyWith(extensions: [lichessCustomColors.harmonized(theme.colorScheme)]);
}
