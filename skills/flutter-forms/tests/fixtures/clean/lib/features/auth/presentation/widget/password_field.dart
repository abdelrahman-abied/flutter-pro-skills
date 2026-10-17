import 'package:flutter/material.dart';

/// Toggleable password field: keyboard learning off while visible, autofill on.
class PasswordField extends StatefulWidget {
  const PasswordField({super.key, required this.controller, this.isNew = false});

  final TextEditingController controller;
  final bool isNew;

  @override
  State<PasswordField> createState() => _PasswordFieldState();
}

class _PasswordFieldState extends State<PasswordField> {
  bool _hidden = true;

  @override
  Widget build(BuildContext context) {
    return TextFormField(
      controller: widget.controller,
      obscureText: _hidden,
      enableSuggestions: false,
      autocorrect: false,
      enableIMEPersonalizedLearning: false,
      autofillHints: [widget.isNew ? AutofillHints.newPassword : AutofillHints.password],
      maxLength: 128,
      decoration: InputDecoration(
        labelText: 'Password',
        counterText: '',
        suffixIcon: IconButton(
          tooltip: _hidden ? 'Show password' : 'Hide password',
          icon: Icon(_hidden ? Icons.visibility : Icons.visibility_off),
          onPressed: () => setState(() => _hidden = !_hidden),
        ),
      ),
      validator: (v) => (v == null || v.isEmpty) ? 'Enter your password' : null,
    );
  }
}
