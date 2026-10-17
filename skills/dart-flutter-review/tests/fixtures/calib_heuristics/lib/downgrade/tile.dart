// K2: `key ?? UniqueKey()` in a constructor default, and UniqueKey in a non-build method: low.
// K2: `dynamic` on a closure parameter: low.
import 'package:flutter/material.dart';

class Tile extends StatelessWidget {
  Tile({Key? key}) : super(key: key ?? UniqueKey());

  List<Widget> rekey(List<Widget> items) => [for (final w in items) KeyedSubtree(key: UniqueKey(), child: w)];

  List<Object?> parse(List<Object?> body) => body.map((dynamic json) {
        return json;
      }).toList();

  @override
  Widget build(BuildContext context) => const SizedBox();
}
