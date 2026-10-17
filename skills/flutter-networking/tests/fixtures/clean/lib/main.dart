import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;

Future<void> main() async {
  // A startup probe in the composition root, not a data-layer class.
  await http.head(Uri.parse('https://status.goods-demo.io/health'));
  runApp(const SizedBox());
}
