import 'package:flutter/material.dart';

class Badge extends StatelessWidget {
  const Badge({super.key});

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        // ds-ignore: DS-001 brand red is fixed by the partner's guidelines
        const ColoredBox(color: Color(0xFFE53935)),
        const ColoredBox(color: Colors.purple), // ds-ignore: DS-001 legacy screen, replaced in Q3
        const Text('x', style: TextStyle(fontSize: 13)),
      ],
    );
  }
}
