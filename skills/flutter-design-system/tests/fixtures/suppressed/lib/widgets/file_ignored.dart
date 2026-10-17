// ds-ignore-file: DS-002 marketing page with its own type scale
import 'package:flutter/material.dart';

class Promo extends StatelessWidget {
  const Promo({super.key});

  @override
  Widget build(BuildContext context) => const Text('Sale', style: TextStyle(fontSize: 40));
}
