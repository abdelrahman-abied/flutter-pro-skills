// i18n-ignore-file: I18N-012 the chess board is physical: it never mirrors
import 'package:flutter/material.dart';

class Board extends StatelessWidget {
  const Board({super.key});

  @override
  Widget build(BuildContext context) {
    return const Stack(
      children: [
        Positioned(left: 0, top: 0, child: SizedBox()),
        Align(alignment: Alignment.topLeft, child: SizedBox()),
      ],
    );
  }
}
