import 'dart:math';

import 'package:flutter/material.dart';

// FP 1: a fixed 5x5 grid whose count comes from a getter over constants is bounded (PERF-001 must not fire).
class PhotoGrid extends StatelessWidget {
  const PhotoGrid({super.key});

  static const int _gridSize = 5;
  int get _imgCount => pow(_gridSize, 2).round();

  @override
  Widget build(BuildContext context) {
    return GridView.count(
      physics: const NeverScrollableScrollPhysics(),
      crossAxisCount: _gridSize,
      children: List.generate(_imgCount, (i) => Text('$i')),
    );
  }
}

// TP 1: a log that grows without bound, built eagerly (PERF-001 still fires).
class LogView extends StatelessWidget {
  const LogView({super.key, required this.log});

  final List<String> log;

  @override
  Widget build(BuildContext context) {
    return ListView(children: log.map<Widget>((o) => Text(o)).toList(growable: false));
  }
}
