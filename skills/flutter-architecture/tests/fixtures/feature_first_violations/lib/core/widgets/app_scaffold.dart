import 'package:flutter/material.dart';

import 'package:feature_first_violations/features/auth/presentation/auth_badge.dart';

class AppScaffold extends StatelessWidget {
  const AppScaffold({super.key});

  @override
  Widget build(BuildContext context) => const Scaffold(body: AuthBadge());
}
