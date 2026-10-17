import 'package:flutter/material.dart';

class Item {
  Item(this.id) : color = Colors.primaries[id % Colors.primaries.length];
  final int id;
  final Color color;
}
