import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import 'core/router/routes_table.dart';
import 'features/auth/presentation/notifier/auth_notifier.dart';

void main() => runApp(const ProviderScope(child: App()));

class App extends ConsumerWidget {
  const App({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return MaterialApp.router(
      routerConfig: GoRouter(
        debugLogDiagnostics: true,
        redirect: (context, state) {
          final signedIn = ref.read(authNotifierProvider).isSignedIn;
          return signedIn ? null : '/login';
        },
        routes: appRoutes,
      ),
    );
  }
}
