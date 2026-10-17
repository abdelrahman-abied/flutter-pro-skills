// K3 A9: jsonDecode on a local string is not I/O; on a response body it is
import 'dart:convert';
import 'package:flutter/widgets.dart';

class JsonScreen extends StatelessWidget {
  const JsonScreen({super.key, required this.raw, required this.response});
  final String raw;
  final dynamic response;
  @override
  Widget build(BuildContext context) {
    final a = jsonDecode(raw);
    final b = jsonDecode(response.body);
    return Text('$a $b');
  }
}
