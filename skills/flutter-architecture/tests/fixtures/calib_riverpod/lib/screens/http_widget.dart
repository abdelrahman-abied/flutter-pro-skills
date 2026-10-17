// K3 FN: ARCH-101 call shapes `widget.httpClient!.post(` and `Socket.connect(`
import 'dart:io';
import 'package:flutter/widgets.dart';

class HttpWidget extends StatefulWidget {
  const HttpWidget({super.key, this.httpClient});
  final dynamic httpClient;
  @override
  State<HttpWidget> createState() => _HttpWidgetState();
}

class _HttpWidgetState extends State<HttpWidget> {
  Future<void> send() async {
    await widget.httpClient!.post(Uri.parse('https://x'));
    await Socket.connect('localhost', 80);
  }

  @override
  Widget build(BuildContext context) => const SizedBox();
}
