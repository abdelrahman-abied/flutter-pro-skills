import 'package:flutter/material.dart';

import 'src/brand.dart';

void main() => runApp(MaterialApp(
    theme: ThemeData(brightness: Brightness.light, extensions: const [Brand(accent: Color(0xFFED1D24))])));
