import 'package:flutter/material.dart';

class SplitPane extends StatelessWidget {
  const SplitPane({super.key});

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(
      builder: (context, constraints) {
        // adapt-ignore: ADAPT-004 this component's own minimum, not a window breakpoint
        if (constraints.maxWidth > 720) return const Row();
        if (constraints.maxWidth > 480) return const Column();
        return const SizedBox();
      },
    );
  }
}
