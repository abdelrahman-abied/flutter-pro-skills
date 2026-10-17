import 'package:flutter/foundation.dart';
import 'package:flutter/widgets.dart';
import 'package:go_router/go_router.dart';
import 'package:riverpod_annotation/riverpod_annotation.dart';

import '../../features/auth/presentation/notifier/auth_notifier.dart';
import '../../features/shop/presentation/view/shop_views.dart';
import 'routes.dart';

part 'app_router.g.dart';

@Riverpod(keepAlive: true)
GoRouter appRouter(Ref ref) {
  final refresh = ValueNotifier<AuthState?>(null);
  ref.listen(authNotifierProvider, (_, next) => refresh.value = next);
  ref.onDispose(refresh.dispose);

  return GoRouter(
    debugLogDiagnostics: kDebugMode,
    refreshListenable: refresh,
    redirect: (context, state) {
      final signedIn = ref.read(authNotifierProvider).isSignedIn;
      final atLogin = state.matchedLocation == Routes.login;
      if (!signedIn) return atLogin ? null : Routes.login;
      if (atLogin) return Routes.home;
      return null;
    },
    errorBuilder: (context, state) => const NotFoundView(),
    routes: [
      GoRoute(
        path: Routes.home,
        builder: (context, state) => const HomeView(),
        routes: [
          GoRoute(
            path: Routes.productsRelative,
            builder: (context, state) => const ProductsView(),
            routes: [
              GoRoute(
                path: r':id(\d+)',
                builder: (context, state) => ProductView(id: int.parse(state.pathParameters['id']!)),
              ),
              GoRoute(
                path: 'by-code/:code',
                builder: (context, state) {
                  final id = int.tryParse(state.pathParameters['code'] ?? '');
                  return id == null ? const NotFoundView() : ProductView(id: id);
                },
              ),
            ],
          ),
        ],
      ),
      GoRoute(path: Routes.login, builder: (context, state) => const LoginView()),
      GoRoute(
        path: '/search',
        builder: (context, state) => SearchView(query: state.uri.queryParameters['q'] ?? ''),
      ),
      GoRoute(
        path: '/checkout',
        builder: (context, state) {
          final cart = state.extra;
          return cart is Cart ? CheckoutView(cart: cart) : const ProductsView();
        },
      ),
    ],
  );
}
