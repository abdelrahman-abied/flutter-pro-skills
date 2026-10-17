import 'package:flutter/material.dart';

class ErrorIndicator extends StatelessWidget {
  const ErrorIndicator({super.key});

  @override
  Widget build(BuildContext context) {
    return FilledButton(
      style: const ButtonStyle(foregroundColor: WidgetStatePropertyAll(Colors.white)),
      onPressed: () {},
      child: const Text('Retry'),
    );
  }
}
