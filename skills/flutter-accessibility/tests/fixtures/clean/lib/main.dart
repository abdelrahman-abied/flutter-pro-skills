import 'package:flutter/material.dart';

import 'core/theme/app_colors.dart';
import 'features/profile/presentation/view/profile_screen.dart';

void main() => runApp(const App());

class App extends StatelessWidget {
  const App({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      theme: ThemeData(colorScheme: AppColors.light),
      // Clamping at 2.0 still honours the 200% the platforms offer.
      builder: (context, child) => MediaQuery.withClampedTextScaling(maxScaleFactor: 2.0, child: child!),
      home: const ProfileScreen(),
    );
  }
}
