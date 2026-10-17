import 'package:flutter/material.dart';

// Not reported by SEC-004: form-field values are flutter-forms FORM-004.
class LoginView extends StatefulWidget {
  const LoginView({super.key});

  @override
  State<LoginView> createState() => _LoginViewState();
}

class _LoginViewState extends State<LoginView> {
  final _passwordController = TextEditingController();

  @override
  void dispose() {
    _passwordController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return TextField(
      controller: _passwordController,
      obscureText: true,
      onChanged: (password) => debugPrint('typed $password'),
      onSubmitted: (_) => print('submit ${_passwordController.text}'),
    );
  }
}
