import 'package:go_router/go_router.dart';
import 'package:riverpod_annotation/riverpod_annotation.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../../features/auth/presentation/notifier/auth_notifier.dart';
import 'routes_table.dart';

part 'app_router.g.dart';

@riverpod
GoRouter appRouter(Ref ref) {
  final auth = ref.watch(authNotifierProvider);
  return GoRouter(
    redirect: (context, state) async {
      final prefs = await SharedPreferences.getInstance();
      final onboarded = prefs.getBool('onboarded') ?? false;
      if (!onboarded) return '/onboarding';
      return auth.isSignedIn ? null : '/login';
    },
    routes: appRoutes,
  );
}
