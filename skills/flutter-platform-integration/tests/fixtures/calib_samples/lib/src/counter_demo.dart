import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'counter_channel.dart';

class CounterDemo extends StatefulWidget {
  const CounterDemo({super.key});

  @override
  State<CounterDemo> createState() => _CounterDemoState();
}

class _CounterDemoState extends State<CounterDemo> {
  int count = 0;
  String label = '';

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    const BasicMessageChannel<String?>('sampleLabels', StringCodec()).setMessageHandler((message) async {
      setState(() => label = message ?? '');
      return null;
    });
  }

  @override
  Widget build(BuildContext context) {
    return FilledButton(
      onPressed: () async {
        try {
          final value = await Counter.increment(value: count);
          setState(() => count = value);
        } catch (error) {
          if (!context.mounted) return;
          ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('$error')));
        }
      },
      child: Text('$count $label'),
    );
  }
}

class HostCounterModel extends ChangeNotifier {
  HostCounterModel() {
    _channel.setMethodCallHandler(_onCall);
  }

  final _channel = const MethodChannel('sampleHostCounter');
  int count = 0;

  void increment() {
    _channel.invokeMethod<void>('incrementCounter');
  }

  Future<dynamic> _onCall(MethodCall call) async {
    count = call.arguments as int;
    notifyListeners();
  }
}
