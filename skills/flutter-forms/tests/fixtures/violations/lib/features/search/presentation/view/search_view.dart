import 'package:flutter/material.dart';

class SearchView extends StatelessWidget {
  const SearchView({super.key, required this.onSearch});

  final ValueChanged<String> onSearch;

  @override
  Widget build(BuildContext context) {
    return TextField(
      controller: TextEditingController(text: 'Search...'),
      focusNode: FocusNode(),
      onSubmitted: onSearch,
    );
  }
}
