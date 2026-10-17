import 'package:flutter/material.dart';

import 'core/theme/app_colors.dart';
import 'features/profile/presentation/view/profile_view.dart';

void main() => runApp(const App());

class App extends StatelessWidget {
  const App({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      theme: ThemeData(colorScheme: AppColors.light),
      builder: (context, child) => MediaQuery(
        data: MediaQuery.of(context).copyWith(textScaler: TextScaler.noScaling),
        child: child!,
      ),
      home: const ProfileView(),
    );
  }
}
