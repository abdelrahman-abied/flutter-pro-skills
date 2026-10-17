import 'package:flutter/widgets.dart';
import 'package:go_router/go_router.dart';

import '../../features/shop/presentation/view/shop_views.dart';
import 'routes.dart';

final appRoutes = <RouteBase>[
  GoRoute(
    path: Routes.home,
    builder: (context, state) => const HomeView(),
    routes: [
      GoRoute(
        path: Routes.productsRelative,
        builder: (context, state) => const ProductsView(),
        routes: [
          GoRoute(
            path: ':id',
            builder: (context, state) {
              final id = int.parse(state.pathParameters['id']!);
              return ProductView(id: id);
            },
          ),
        ],
      ),
    ],
  ),
  GoRoute(path: '/products', builder: (context, state) => const ProductsView()),
  GoRoute(path: Routes.login, builder: (context, state) => const LoginPlaceholder()),
  GoRoute(path: '/reset/:token', builder: (context, state) => const LoginPlaceholder()),
  GoRoute(
    path: Routes.search,
    builder: (context, state) => SearchView(query: state.uri.queryParameters['q']!),
  ),
  GoRoute(
    path: '/gift',
    builder: (context, state) => GiftView(gift: state.extra is Gift ? state.extra as Gift : null),
  ),
  GoRoute(path: '/checkout', builder: (context, state) => CheckoutView(cart: state.extra as Cart)),
];
