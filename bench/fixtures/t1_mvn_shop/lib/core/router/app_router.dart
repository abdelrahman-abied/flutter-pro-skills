import 'package:flutter/foundation.dart';
import 'package:go_router/go_router.dart';
import 'package:riverpod_annotation/riverpod_annotation.dart';

import '../../features/auth/presentation/notifier/auth_notifier.dart';
import '../../features/auth/presentation/state/auth_state.dart';
import '../../features/auth/presentation/view/login_view.dart';
import '../../features/cart/presentation/view/cart_view.dart';
import '../../features/order/presentation/view/order_history_view.dart';
import '../../features/product/presentation/view/product_detail_view.dart';
import '../../features/product/presentation/view/product_list_view.dart';
import '../../features/profile/presentation/view/profile_view.dart';

part 'app_router.g.dart';

@Riverpod(keepAlive: true)
GoRouter appRouter(Ref ref) {
  final auth = ValueNotifier<AuthState>(ref.read(authProvider));
  ref
    ..onDispose(auth.dispose)
    ..listen(authProvider, (_, next) => auth.value = next);

  return GoRouter(
    initialLocation: '/login',
    refreshListenable: auth,
    redirect: (context, state) {
      final signedIn = auth.value is AuthSuccess;
      final atLogin = state.matchedLocation == '/login';
      if (!signedIn && !atLogin) return '/login';
      if (signedIn && atLogin) return '/products';
      return null;
    },
    routes: [
      GoRoute(path: '/login', builder: (context, state) => const LoginView()),
      GoRoute(
        path: '/products',
        builder: (context, state) => const ProductListView(),
        routes: [
          GoRoute(
            path: ':id',
            builder: (context, state) {
              final id = int.parse(state.pathParameters['id']!);
              return ProductDetailView(productId: id);
            },
          ),
        ],
      ),
      GoRoute(path: '/cart', builder: (context, state) => const CartView()),
      GoRoute(
        path: '/orders',
        builder: (context, state) => const OrderHistoryView(),
      ),
      GoRoute(
          path: '/profile', builder: (context, state) => const ProfileView()),
    ],
  );
}
