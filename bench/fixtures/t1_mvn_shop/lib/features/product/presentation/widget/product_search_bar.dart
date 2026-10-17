import 'package:flutter/material.dart';

import '../../../../l10n/gen/app_localizations.dart';

class ProductSearchBar extends StatefulWidget {
  const ProductSearchBar({super.key, required this.onSearch});

  final ValueChanged<String> onSearch;

  @override
  State<ProductSearchBar> createState() => _ProductSearchBarState();
}

class _ProductSearchBarState extends State<ProductSearchBar> {
  final _controller = TextEditingController();

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.all(12),
      child: TextField(
        controller: _controller,
        textInputAction: TextInputAction.search,
        decoration: InputDecoration(
          hintText: AppLocalizations.of(context)!.searchHint,
          prefixIcon: const Icon(Icons.search),
        ),
        onSubmitted: widget.onSearch,
      ),
    );
  }
}
