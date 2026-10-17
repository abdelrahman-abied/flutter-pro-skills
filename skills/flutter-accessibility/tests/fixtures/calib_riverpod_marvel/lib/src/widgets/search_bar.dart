import 'package:flutter/material.dart';

class SearchBar extends StatelessWidget {
  const SearchBar({super.key, required this.isFocused});

  final bool isFocused;

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        // FP fixed: hidden only while the field is collapsed; the reader reaches it once focused.
        ExcludeSemantics(
          excluding: !isFocused,
          child: const TextField(),
        ),
        // TP kept: always hidden.
        ExcludeSemantics(
          child: const TextField(),
        ),
      ],
    );
  }
}
