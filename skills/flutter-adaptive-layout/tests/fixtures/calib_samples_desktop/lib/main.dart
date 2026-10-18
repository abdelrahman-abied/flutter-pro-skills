import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

void main() {
  runApp(const MaterialApp(home: SearchHome()));
}

class SearchHome extends StatelessWidget {
  const SearchHome({super.key});

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        const Text('Search'),
        if (!Platform.isMacOS) TextButton(onPressed: SystemNavigator.pop, child: const Text('Quit')),
      ],
    );
  }
}
