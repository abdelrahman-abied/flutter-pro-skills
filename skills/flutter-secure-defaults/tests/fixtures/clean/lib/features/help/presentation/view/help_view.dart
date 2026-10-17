import 'package:flutter/material.dart';
import 'package:webview_flutter/webview_flutter.dart';

const _allowedHosts = {'help.shop.dev'};

bool _isAllowed(Uri uri) => uri.scheme == 'https' && _allowedHosts.contains(uri.host);

class HelpView extends StatefulWidget {
  const HelpView({super.key, required this.url});
  final Uri url;

  @override
  State<HelpView> createState() => _HelpViewState();
}

class _HelpViewState extends State<HelpView> {
  late final WebViewController _controller = WebViewController()
    ..setJavaScriptMode(JavaScriptMode.unrestricted)
    ..setNavigationDelegate(NavigationDelegate(
      onNavigationRequest: (request) =>
          _isAllowed(Uri.parse(request.url)) ? NavigationDecision.navigate : NavigationDecision.prevent,
    ));

  @override
  void initState() {
    super.initState();
    if (_isAllowed(widget.url)) _controller.loadRequest(widget.url);
  }

  @override
  Widget build(BuildContext context) => WebViewWidget(controller: _controller);
}
