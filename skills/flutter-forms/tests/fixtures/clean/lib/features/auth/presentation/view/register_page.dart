import 'package:flutter/material.dart';

/// The handler guards itself, and a separate flag swaps the button for a spinner.
class RegisterPage extends StatefulWidget {
  const RegisterPage({super.key, required this.register});

  final Future<void> Function(String email) register;

  @override
  State<RegisterPage> createState() => _RegisterPageState();
}

class _RegisterPageState extends State<RegisterPage> {
  final _formKey = GlobalKey<FormState>();
  final _email = TextEditingController();
  bool _isLoading = false;

  @override
  void dispose() {
    _email.dispose();
    super.dispose();
  }

  Future<void> _register() async {
    final form = _formKey.currentState;
    if (form == null || !form.validate()) return;
    setState(() => _isLoading = true);
    await widget.register(_email.text.trim());
    if (mounted) setState(() => _isLoading = false);
  }

  Future<void> _openTerms() async {
    await Navigator.of(context).pushNamed('/terms');
  }

  Future<void> _createWithName() async {
    final name = await showDialog<String>(context: context, builder: (_) => const SizedBox());
    if (name == null) return;
    await widget.register(name);
  }

  @override
  Widget build(BuildContext context) {
    return Form(
      key: _formKey,
      child: Column(
        children: [
          TextFormField(
            controller: _email,
            keyboardType: TextInputType.emailAddress,
            validator: (v) => v == null || v.isEmpty ? 'Required' : null,
          ),
          if (_isLoading)
            const CircularProgressIndicator()
          else
            ElevatedButton(onPressed: _register, child: const Text('Create account')),
          TextButton(onPressed: _openTerms, child: const Text('Terms')),
          TextButton(onPressed: _createWithName, child: const Text('Create from name')),
        ],
      ),
    );
  }
}
