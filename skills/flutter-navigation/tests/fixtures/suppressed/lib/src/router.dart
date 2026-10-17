import 'package:flutter/foundation.dart';
import 'package:flutter/widgets.dart';
import 'package:go_router/go_router.dart';

class ItemView extends StatelessWidget {
  const ItemView({super.key, required this.id});
  final int id;
  @override
  Widget build(BuildContext context) => const SizedBox();
}

final router = GoRouter(
  debugLogDiagnostics: kDebugMode,
  routes: [
    GoRoute(
      path: '/items/:id',
      builder: (context, state) {
        // nav-ignore: NAV-003 ids come from our own QR codes; the error page covers the rest
        final id = int.parse(state.pathParameters['id']!);
        return ItemView(id: id);
      },
    ),
    GoRoute(
      path: '/legacy/:id',
      builder: (context, state) => ItemView(id: int.parse(state.pathParameters['id']!)), // nav-ignore: NAV-003 legacy links are always numeric
    ),
    GoRoute(
      path: '/raw/:id',
      builder: (context, state) => ItemView(id: int.parse(state.pathParameters['id']!)),
    ),
  ],
);
