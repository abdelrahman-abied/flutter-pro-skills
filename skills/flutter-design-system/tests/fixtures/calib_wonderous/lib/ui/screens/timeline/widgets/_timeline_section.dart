import 'package:flutter/material.dart';

class TimelineSection extends StatelessWidget {
  const TimelineSection({super.key});

  @override
  Widget build(BuildContext context) {
    return Column(children: [
      ClipRRect(borderRadius: BorderRadius.circular(99), child: const Placeholder()),
      ClipRRect(borderRadius: BorderRadius.circular(10), child: const Placeholder()),
    ]);
  }
}
