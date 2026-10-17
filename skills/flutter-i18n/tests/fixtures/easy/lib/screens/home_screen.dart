import 'package:easy_localization/easy_localization.dart';
import 'package:flutter/material.dart';

class HomeScreen extends StatelessWidget {
  const HomeScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        Text('home.title'.tr()),
        Text('home.welcome').tr(namedArgs: {'name': 'Sara'}),
        Text(tr('logout') + ' now'),
        const Text('Hello world'),
        Text(plural('items', 3)),
      ],
    );
  }
}
