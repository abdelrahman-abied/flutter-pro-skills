// a11y-ignore-file: A11Y-004 the clock face is sized to its dial and has a scalable text alternative
import 'package:flutter/material.dart';

class ClockFace extends StatelessWidget {
  const ClockFace({super.key});

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        Text('12', textScaler: TextScaler.noScaling),
        Text('6', textScaler: TextScaler.linear(1.0)),
      ],
    );
  }
}
