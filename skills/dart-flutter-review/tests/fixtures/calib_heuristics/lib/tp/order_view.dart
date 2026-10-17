// True positives that must keep firing after the calibration fixes.
import 'package:flutter/material.dart';

Future<int> load() async => 1;

class OrderView extends StatefulWidget {
  const OrderView({super.key});
  @override
  State<OrderView> createState() => _OrderViewState();
}

class _OrderViewState extends State<OrderView> {
  final _note = TextEditingController();

  String getName() => 'order';

  void onTap() {}

  Future<int> total() {
    return load().then((v) => v * 2);
  }

  Future<void> save() async {
    load().then((v) => debugPrint('$v'));
  }

  Widget _buildRow() => const Text('row');

  @override
  Widget build(BuildContext context) {
    return Container(
      key: UniqueKey(),
      color: Color(0xFF123456),
      child: FutureBuilder<int>(
        future: load(),
        builder: (context, snapshot) => StreamBuilder<Map<String, List<int>>>(
          stream: watchTotals(),
          builder: (context, totals) => _buildRow(),
        ),
      ),
    );
  }
}

Stream<Map<String, List<int>>> watchTotals() => const Stream.empty();
