import 'package:flutter/material.dart';

class SideIndicator extends StatelessWidget {
  const SideIndicator({super.key});

  @override
  Widget build(BuildContext context) {
    final isLight = Theme.of(context).brightness == Brightness.light;
    return Icon(Icons.circle, color: isLight ? context.colorScheme.primary : context.colorScheme.secondary);
  }
}

extension on BuildContext {
  ColorScheme get colorScheme => Theme.of(this).colorScheme;
}
