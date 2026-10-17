import 'package:flutter/material.dart';

class const Board({super.key, required final int size}) extends StatelessWidget {
  @override
  Widget build(BuildContext context) => SizedBox(width: size * 8.0);
}
