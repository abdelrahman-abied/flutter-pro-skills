import 'package:flutter/material.dart';

class CatalogTile extends StatefulWidget {
  const CatalogTile({super.key});

  @override
  State<CatalogTile> createState() => _CatalogTileState();
}

class _CatalogTileState extends State<CatalogTile> {
  bool _hovered = false;

  @override
  Widget build(BuildContext context) {
    final columns = MediaQuery.sizeOf(context).width >= 840 ? 3 : 1;
    return MouseRegion(
      onEnter: (_) => setState(() => _hovered = true),
      onExit: (_) => setState(() => _hovered = false),
      child: Stack(
        children: [
          Text('columns: $columns'),
          if (_hovered)
            IconButton(icon: const Icon(Icons.delete), onPressed: () {}),
        ],
      ),
    );
  }
}
