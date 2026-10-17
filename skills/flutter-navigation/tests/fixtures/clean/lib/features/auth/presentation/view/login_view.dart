import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../../../core/router/routes.dart';

const _allowedSchemes = {'https', 'mailto'};

class LoginView extends StatelessWidget {
  const LoginView({super.key});

  void _afterSignIn(BuildContext context) {
    final from = GoRouterState.of(context).uri.queryParameters['from'];
    final safe = from != null && from.startsWith('/') && !from.startsWith('//');
    context.go(safe ? from : Routes.home);
  }

  Future<void> _openHelp(GoRouterState state) async {
    final uri = Uri.tryParse(state.uri.queryParameters['help'] ?? '');
    if (uri == null || !_allowedSchemes.contains(uri.scheme)) return;
    await launchUrl(uri, mode: LaunchMode.externalApplication);
  }

  String? _section(Uri uri) => uri.pathSegments.length > 1 ? uri.pathSegments[1] : null;

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        TextButton(onPressed: () => _afterSignIn(context), child: const Text('Continue')),
        TextButton(onPressed: () => context.go(Routes.product(42)), child: const Text('Product')),
        TextButton(onPressed: () => _openHelp(GoRouterState.of(context)), child: const Text('Help')),
        Text(_section(GoRouterState.of(context).uri) ?? ''),
      ],
    );
  }
}
