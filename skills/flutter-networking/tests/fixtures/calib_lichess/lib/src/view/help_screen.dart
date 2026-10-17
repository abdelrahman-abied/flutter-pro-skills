import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';

class HelpScreen extends StatelessWidget {
  const HelpScreen({required this.path, super.key});

  final String path;

  @override
  Widget build(BuildContext context) => Column(children: [
        TextButton(onPressed: () => launchUrl(Uri.parse('https://board-demo.org/help')), child: const Text('Help')),
        TextButton(onPressed: () => launchUrl(Uri.https('board-demo.org').resolve(path)), child: const Text('More')),
      ]);
}
