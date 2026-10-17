import 'package:flutter/widgets.dart';
import 'package:go_router/go_router.dart';
import 'package:url_launcher/url_launcher.dart';

class LinkView extends StatelessWidget {
  const LinkView({super.key});

  void _openTarget(GoRouterState state) {
    final target = state.uri.queryParameters['url'];
    if (target != null) {
      launchUrl(Uri.parse(target));
    }
  }

  String _section(Uri uri) => uri.pathSegments[1];

  @override
  Widget build(BuildContext context) {
    _openTarget(GoRouterState.of(context));
    return Text(_section(GoRouterState.of(context).uri));
  }
}
