import 'package:flutter/material.dart';

void main() => runApp(const MaterialApp(home: Scaffold(body: Text('Hello world'))));

class Hello extends StatelessWidget {
  const Hello({super.key});

  @override
  Widget build(BuildContext context) => const Padding(
        padding: EdgeInsets.only(left: 16),
        child: Text('Not localised, so not reported'),
      );
}
