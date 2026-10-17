import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../widget/password_field.dart';

/// setState version: busy flag guards the submit; the form key is validated.
class LoginPage extends StatefulWidget {
  const LoginPage({super.key, required this.signIn});

  final Future<void> Function(String email, String password) signIn;

  @override
  State<LoginPage> createState() => _LoginPageState();
}

class _LoginPageState extends State<LoginPage> {
  final _formKey = GlobalKey<FormState>();
  late final TextEditingController _emailController;
  late final TextEditingController _passwordController;
  late final FocusNode _passwordFocus;
  bool _submitting = false;

  @override
  void initState() {
    super.initState();
    _emailController = TextEditingController();
    _passwordController = TextEditingController();
    _passwordFocus = FocusNode();
  }

  @override
  void dispose() {
    _emailController.dispose();
    _passwordController.dispose();
    _passwordFocus.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    if (_submitting) return;
    if (!_formKey.currentState!.validate()) return;
    debugPrint('login submitted (email length ${_emailController.text.length})');
    setState(() => _submitting = true);
    try {
      await widget.signIn(_emailController.text.trim(), _passwordController.text);
      TextInput.finishAutofillContext();
    } finally {
      if (mounted) setState(() => _submitting = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return AutofillGroup(
      child: Form(
        key: _formKey,
        child: Column(
          children: [
            TextFormField(
              controller: _emailController,
              keyboardType: TextInputType.emailAddress,
              autofillHints: const [AutofillHints.email],
              textInputAction: TextInputAction.next,
              onFieldSubmitted: (_) => _passwordFocus.requestFocus(),
              decoration: const InputDecoration(labelText: 'Email'),
              validator: (v) => (v == null || !v.contains('@')) ? 'Enter a valid email' : null,
            ),
            PasswordField(controller: _passwordController),
            TextFormField(
              decoration: const InputDecoration(labelText: 'Password hint (optional)'),
              maxLength: 60,
            ),
            FilledButton(
              onPressed: _submitting ? null : _submit,
              child: _submitting ? const CircularProgressIndicator() : const Text('Sign in'),
            ),
          ],
        ),
      ),
    );
  }
}
