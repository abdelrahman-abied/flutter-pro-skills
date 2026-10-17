import 'package:flutter/material.dart';

class Buttons extends StatelessWidget {
  const Buttons({super.key});

  @override
  Widget build(BuildContext context) {
    final isBright = Theme.of(context).brightness == Brightness.light;
    return ColoredBox(color: isBright ? Theme.of(context).colorScheme.surface : Theme.of(context).colorScheme.surfaceDim);
  }
}
