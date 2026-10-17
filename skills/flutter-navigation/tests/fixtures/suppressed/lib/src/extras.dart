// nav-ignore-file: NAV-004 this route table is only reached by in-app push, never by URL
import 'package:flutter/widgets.dart';
import 'package:go_router/go_router.dart';

class Draft {}

class DraftView extends StatelessWidget {
  const DraftView({super.key, required this.draft});
  final Draft draft;
  @override
  Widget build(BuildContext context) => const SizedBox();
}

final draftRoutes = [
  GoRoute(path: '/draft', builder: (context, state) => DraftView(draft: state.extra as Draft)),
  GoRoute(path: '/draft2', builder: (context, state) => DraftView(draft: state.extra! as Draft)),
];
