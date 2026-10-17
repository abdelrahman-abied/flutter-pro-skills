import 'package:flutter/material.dart';

class EditDialog extends StatelessWidget {
  const EditDialog({super.key, required this.isUrlField});

  final bool isUrlField;

  @override
  Widget build(BuildContext context) {
    // FP fixed: the two autofocus fields are alternatives of a ternary; only one is built.
    return AlertDialog(
      content: isUrlField
          ? const TextField(autofocus: true, keyboardType: TextInputType.url)
          : const TextField(autofocus: true),
    );
  }
}

class TwoFields extends StatelessWidget {
  const TwoFields({super.key});

  @override
  Widget build(BuildContext context) {
    // TP kept: both are built, both ask for focus.
    return const Column(
      children: [
        TextField(autofocus: true),
        TextField(autofocus: true),
      ],
    );
  }
}
