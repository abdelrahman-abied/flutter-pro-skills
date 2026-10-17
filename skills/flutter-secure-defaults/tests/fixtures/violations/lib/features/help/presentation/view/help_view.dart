import 'package:flutter/material.dart';
import 'package:webview_flutter/webview_flutter.dart';

// SEC-007: JavaScript on, no navigation guard.
class HelpView extends StatefulWidget {
  const HelpView({super.key, required this.url});
  final String url;

  @override
  State<HelpView> createState() => _HelpViewState();
}

class _HelpViewState extends State<HelpView> {
  late final WebViewController _controller = WebViewController()
    ..setJavaScriptMode(JavaScriptMode.unrestricted)
    ..loadRequest(Uri.parse(widget.url));

  @override
  Widget build(BuildContext context) => WebViewWidget(controller: _controller);
}
