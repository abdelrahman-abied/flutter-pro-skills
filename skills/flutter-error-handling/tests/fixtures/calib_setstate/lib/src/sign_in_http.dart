import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;

class SignInHttpDemo extends StatefulWidget {
  const SignInHttpDemo({this.httpClient, super.key});
  final http.Client? httpClient;
  @override
  State<SignInHttpDemo> createState() => _SignInHttpDemoState();
}

class _SignInHttpDemoState extends State<SignInHttpDemo> {
  String _status = '';

  @override
  Widget build(BuildContext context) {
    return Column(children: [
      Text(_status),
      TextButton(
        child: const Text('Sign in'),
        // ERR-014: a network call awaited in a UI callback with no try/catch.
        onPressed: () async {
          final result = await widget.httpClient!.post(Uri.parse('https://example.com/signin'));
          setState(() => _status = '${result.statusCode}');
        },
      ),
      TextButton(
        child: const Text('Sign in safely'),
        onPressed: () async {
          try {
            final result = await widget.httpClient!.post(Uri.parse('https://example.com/signin'));
            setState(() => _status = '${result.statusCode}');
          } on http.ClientException {
            setState(() => _status = 'Network problem, try again');
          }
        },
      ),
    ]);
  }
}
