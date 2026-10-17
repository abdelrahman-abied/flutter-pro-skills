import 'package:flutter/material.dart';

import '../brand.dart';

class SearchBar extends StatelessWidget {
  const SearchBar({super.key, required this.isFocused});
  final bool isFocused;

  @override
  Widget build(BuildContext context) {
    final accent = Theme.of(context).extension<Brand>()!.accent;
    return AnimatedTheme(
      data: isFocused ? ThemeData.light() : ThemeData.dark(),
      child: Icon(Icons.search, color: accent),
    );
  }
}
