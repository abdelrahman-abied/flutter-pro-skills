import 'package:flutter/material.dart';

class Brand extends StatelessWidget {
  const Brand({super.key});

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        // i18n-ignore: I18N-010 product name, never translated
        const Text('Acme Super Store'),
        const Text('Acme Pay Wallet'), // i18n-ignore: I18N-010 product name
        const Text('Please sign in again'),
      ],
    );
  }
}
