import 'package:flutter/material.dart';

class LoginScreen extends StatefulWidget {
  const LoginScreen({super.key, required this.signIn});
  final Future<void> Function() signIn;
  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen> {
  String? _message;

  Future<void> _submit() async {
    try {
      await widget.signIn();
    } catch (e) {
      // K1: the condition is a comparison, only the displayed text is ERR-008, once per catch block.
      final message = e.toString().contains('ApiException')
          ? 'Sign-in service unavailable'
          : 'Google Sign In error: $e';
      setState(() => _message = '$message ($e)');
    }
  }

  @override
  Widget build(BuildContext context) =>
      TextButton(onPressed: _submit, child: Text(_message ?? 'Sign in'));
}
