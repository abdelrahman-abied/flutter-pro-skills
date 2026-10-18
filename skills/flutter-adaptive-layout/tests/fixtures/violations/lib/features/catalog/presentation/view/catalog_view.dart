import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';

import '../widgets/catalog_tile.dart';

class CatalogView extends StatelessWidget {
  const CatalogView({super.key});

  @override
  Widget build(BuildContext context) {
    final icon = Platform.isIOS ? Icons.arrow_back_ios : Icons.arrow_back;
    final wide = MediaQuery.orientationOf(context) == Orientation.landscape;
    return Scaffold(
      appBar: AppBar(leading: Icon(icon)),
      body: LayoutBuilder(
        builder: (context, constraints) {
          if (constraints.maxWidth > 600) {
            return const Row(children: [Expanded(child: CatalogTile()), Expanded(child: CatalogTile())]);
          }
          return wide ? const CatalogTile() : const SizedBox.shrink();
        },
      ),
    );
  }
}

class CatalogMenu extends StatelessWidget {
  const CatalogMenu({super.key});

  @override
  Widget build(BuildContext context) {
    final showQuit = !kIsWeb && Platform.isMacOS;
    return showQuit ? const Text('Quit') : const SizedBox.shrink();
  }
}
