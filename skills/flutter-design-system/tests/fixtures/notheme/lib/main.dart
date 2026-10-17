import 'package:flutter/material.dart';

void main() => runApp(const MaterialApp(home: Counter()));

class Counter extends StatelessWidget {
  const Counter({super.key});

  @override
  Widget build(BuildContext context) {
    return const Text('0', style: TextStyle(fontSize: 48, color: Colors.blue));
  }
}
