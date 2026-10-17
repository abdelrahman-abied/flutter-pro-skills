import 'package:flutter/material.dart';

class Toolbar extends StatelessWidget {
  const Toolbar({super.key});

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        // a11y-ignore: A11Y-001 the parent ListTile announces this action
        IconButton(icon: const Icon(Icons.more_vert), onPressed: () {}),
        IconButton(
          icon: const Icon(Icons.share),
          onPressed: () {}, // a11y-ignore: A11Y-001 covered by the row's MergeSemantics in the caller
        ),
        Image.asset('assets/logo.png'),
        IconButton(icon: const Icon(Icons.delete), onPressed: () {}),
      ],
    );
  }
}
