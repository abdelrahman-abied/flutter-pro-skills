import 'package:flutter/material.dart';
import 'package:flutter_inappwebview/flutter_inappwebview.dart';

// SEC-007: shouldOverrideUrlLoading is set but never fires without useShouldOverrideUrlLoading: true.
class StatementPage extends StatelessWidget {
  const StatementPage({super.key});

  @override
  Widget build(BuildContext context) {
    return InAppWebView(
      initialUrlRequest: URLRequest(url: WebUri('https://bank.example.com/statement')),
      shouldOverrideUrlLoading: (controller, action) async {
        final host = action.request.url?.host;
        return host == 'bank.example.com' ? NavigationActionPolicy.ALLOW : NavigationActionPolicy.CANCEL;
      },
    );
  }
}
