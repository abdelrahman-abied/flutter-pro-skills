import 'package:go_router/go_router.dart';
import 'package:riverpod_annotation/riverpod_annotation.dart';

import '../../features/product/presentation/view/product_list_view.dart';

part 'app_router.g.dart';

@Riverpod(keepAlive: true)
GoRouter appRouter(Ref ref) {
  return GoRouter(
    initialLocation: '/products',
    routes: [
      GoRoute(
        path: '/products',
        builder: (context, state) => const ProductListView(),
      ),
    ],
  );
}
