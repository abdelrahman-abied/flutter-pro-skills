import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../data/sources/battery_platform_source.dart';

class BatteryView extends ConsumerStatefulWidget {
  const BatteryView({super.key});

  @override
  ConsumerState<BatteryView> createState() => _BatteryViewState();
}

class _BatteryViewState extends ConsumerState<BatteryView> {
  final _channel = const MethodChannel('app.example/battery');
  final _source = BatteryPlatformSource();
  bool _charging = false;
  int _level = 0;

  @override
  void initState() {
    super.initState();
    const EventChannel('app.example/charging').receiveBroadcastStream().listen((event) {
      setState(() => _charging = event == true);
    });
    _channel.setMethodCallHandler((call) async {
      setState(() => _level = call.arguments as int);
    });
  }

  @override
  Widget build(BuildContext context) {
    return TextButton(
      onPressed: () async {
        final level = await _source.level();
        setState(() => _level = level);
      },
      child: Text('$_level $_charging'),
    );
  }
}
