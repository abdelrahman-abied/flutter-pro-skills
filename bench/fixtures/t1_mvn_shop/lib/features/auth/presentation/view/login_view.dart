import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../../l10n/gen/app_localizations.dart';
import '../notifier/auth_notifier.dart';
import '../state/auth_state.dart';

class LoginView extends ConsumerStatefulWidget {
  const LoginView({super.key});

  @override
  ConsumerState<LoginView> createState() => _LoginViewState();
}

class _LoginViewState extends ConsumerState<LoginView> {
  final _formKey = GlobalKey<FormState>();
  final _emailController = TextEditingController();
  final _passwordController = TextEditingController();

  @override
  void dispose() {
    _emailController.dispose();
    _passwordController.dispose();
    super.dispose();
  }

  void _submit() {
    if (!_formKey.currentState!.validate()) return;
    ref.read(authProvider.notifier).login(
          email: _emailController.text.trim(),
          password: _passwordController.text,
        );
  }

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context)!;
    ref.listen<AuthState>(authProvider, (previous, next) {
      if (next is AuthSuccess) context.go('/products');
      if (next is AuthError) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text(l10n.genericError)));
      }
    });
    final state = ref.watch(authProvider);

    return Scaffold(
      appBar: AppBar(title: Text(l10n.loginTitle)),
      body: Form(
        key: _formKey,
        child: ListView(
          padding: const EdgeInsets.all(16),
          children: [
            TextFormField(
              controller: _emailController,
              keyboardType: TextInputType.emailAddress,
              autofillHints: const [AutofillHints.email],
              decoration: InputDecoration(labelText: l10n.emailLabel),
              validator: (v) =>
                  (v == null || !v.contains('@')) ? l10n.invalidEmail : null,
            ),
            const SizedBox(height: 12),
            TextFormField(
              controller: _passwordController,
              autofillHints: const [AutofillHints.password],
              decoration: InputDecoration(labelText: l10n.passwordLabel),
              validator: (v) =>
                  (v == null || v.isEmpty) ? l10n.passwordRequired : null,
            ),
            const SizedBox(height: 24),
            FilledButton(
              onPressed: state is AuthLoading ? null : _submit,
              child: state is AuthLoading
                  ? const SizedBox.square(
                      dimension: 20,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    )
                  : Text(l10n.loginButton),
            ),
          ],
        ),
      ),
    );
  }
}
