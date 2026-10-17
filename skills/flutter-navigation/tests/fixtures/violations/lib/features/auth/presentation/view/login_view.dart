import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

class User {
  const User(this.email);
  final String email;
}

class LoginView extends StatelessWidget {
  const LoginView({super.key, required this.user, required this.accessToken});
  final User user;
  final String accessToken;

  void _afterSignIn(BuildContext context) {
    final from = GoRouterState.of(context).uri.queryParameters['from'];
    context.go(from ?? '/');
  }

  void _openProfile(BuildContext context) {
    context.go('/profile?email=${user.email}');
  }

  void _resume(BuildContext context) {
    context.push('/session/$accessToken');
  }

  @override
  Widget build(BuildContext context) {
    return TextButton(onPressed: () => context.go('/'), child: const Text('Home'));
  }
}
