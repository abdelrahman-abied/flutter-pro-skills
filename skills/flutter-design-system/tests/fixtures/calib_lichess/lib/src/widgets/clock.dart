import 'package:flutter/material.dart';

class ClockStyle {
  const ClockStyle(this.brightness);
  final Brightness brightness;
}

class Clock extends StatelessWidget {
  const Clock({super.key});

  @override
  Widget build(BuildContext context) {
    final brightness = Theme.of(context).brightness;
    final style = ClockStyle(brightness);
    return Text('$style');
  }
}
