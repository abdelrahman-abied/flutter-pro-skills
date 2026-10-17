// SMELLS: undisposed-resource (controller + timer), negative-boolean,
// on-named-method, widget-helper-method, mediaquery-of, eager-children-map,
// future-in-build, opacity-widget, unique-key, hardcoded-color.
// Architecture smells for arch_check: view imports dio and constructs Dio().
import 'dart:async';

import 'package:dio/dio.dart';
import 'package:flutter/material.dart';

class CartView extends StatefulWidget {
  const CartView({super.key, required this.items});

  final List<String> items;

  @override
  State<CartView> createState() => _CartViewState();
}

class _CartViewState extends State<CartView> {
  final _scroll = ScrollController();
  Timer? _poll;
  bool isDisabled = false;

  @override
  void initState() {
    super.initState();
    _poll = Timer.periodic(const Duration(seconds: 30), (_) => setState(() {}));
  }

  void onSubmit() {
    setState(() => isDisabled = true);
  }

  Future<int> fetchCount() async {
    final response = await Dio().get<int>('https://example.com/cart/count');
    return response.data ?? 0;
  }

  Widget _buildHeader() {
    return Opacity(opacity: 0.5, child: Text('${widget.items.length} items'));
  }

  @override
  Widget build(BuildContext context) {
    final width = MediaQuery.of(context).size.width;
    return Container(
      key: UniqueKey(),
      width: width,
      color: Color(0xFF00897B),
      child: Column(
        children: [
          _buildHeader(),
          FutureBuilder<int>(
            future: fetchCount(),
            builder: (context, snapshot) => Text('${snapshot.data}'),
          ),
          Expanded(
            child: ListView(
              controller: _scroll,
              children: widget.items.map((i) => Text(i)).toList(),
            ),
          ),
          ElevatedButton(onPressed: onSubmit, child: const Text('Pay')),
        ],
      ),
    );
  }
}
