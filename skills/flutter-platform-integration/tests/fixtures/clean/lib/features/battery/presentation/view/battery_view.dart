import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

class BatteryView extends StatelessWidget {
  const BatteryView({super.key});

  @override
  Widget build(BuildContext context) {
    return TextButton(
      onPressed: () => SystemChannels.platform.invokeMethod<void>('SystemNavigator.pop'),
      child: const Text('Close'),
    );
  }
}
