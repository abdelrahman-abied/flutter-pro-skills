import 'package:flutter/material.dart';

class ResultCard extends StatelessWidget {
  const ResultCard({super.key, required this.showTitle});
  final bool showTitle;

  @override
  Widget build(BuildContext context) {
    return Stack(
      children: [
        Image.network('https://example.com/a.jpg',
            color: showTitle ? Colors.black.withValues(alpha: 0.5) : null, colorBlendMode: BlendMode.darken),
        const Text('Title', style: TextStyle(shadows: [Shadow(blurRadius: 3.0, color: Colors.black)])),
      ],
    );
  }
}
