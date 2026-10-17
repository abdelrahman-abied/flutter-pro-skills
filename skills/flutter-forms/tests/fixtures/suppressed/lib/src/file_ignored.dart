// form-ignore-file: FORM-004 debug console for the QA build flavour only; this file is excluded from release
import 'package:flutter/material.dart';

class QaConsole extends StatelessWidget {
  const QaConsole({super.key, required this.inputController});

  final TextEditingController inputController;

  @override
  Widget build(BuildContext context) {
    return TextButton(
      onPressed: () {
        print(inputController.text);
        debugPrint('echo ${inputController.text}');
      },
      child: const Text('Echo'),
    );
  }
}
