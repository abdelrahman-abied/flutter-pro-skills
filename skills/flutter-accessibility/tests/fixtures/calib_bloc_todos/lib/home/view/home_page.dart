import 'package:flutter/material.dart';

class HomePage extends StatelessWidget {
  const HomePage({super.key});

  @override
  Widget build(BuildContext context) {
    return const Row(
      children: [
        _TabButton(icon: Icon(Icons.list_rounded, semanticLabel: 'Todos')),
        _TabButton(icon: Icon(Icons.show_chart_rounded, semanticLabel: 'Stats')),
        _BareTabButton(icon: Icon(Icons.settings)),
      ],
    );
  }
}

// FP fixed: the icon is a parameter and every call site passes a labelled Icon.
class _TabButton extends StatelessWidget {
  const _TabButton({required this.icon});

  final Widget icon;

  @override
  Widget build(BuildContext context) {
    return IconButton(onPressed: () {}, iconSize: 32, icon: icon);
  }
}

// TP kept: the forwarded icon is unlabelled at its call site.
class _BareTabButton extends StatelessWidget {
  const _BareTabButton({required this.icon});

  final Widget icon;

  @override
  Widget build(BuildContext context) {
    return IconButton(onPressed: () {}, icon: icon);
  }
}
