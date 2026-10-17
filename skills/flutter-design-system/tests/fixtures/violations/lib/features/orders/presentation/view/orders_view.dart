import 'package:flutter/material.dart';

import '../../../../core/design_system/theme/chart_colors.dart';

class OrdersView extends StatelessWidget {
  const OrdersView({super.key});

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final line = Theme.of(context).extension<ChartColors>()!.line;
    return Container(
      color: isDark ? Colors.grey.shade900 : const Color(0xFFF5F5F5),
      padding: const EdgeInsets.all(13),
      child: Column(
        children: [
          const Text('Orders', style: TextStyle(fontSize: 22, fontWeight: FontWeight.w600)),
          const SizedBox(height: 17),
          DecoratedBox(
            decoration: BoxDecoration(
              color: Colors.deepOrange,
              borderRadius: BorderRadius.circular(10),
              border: Border.all(color: line),
            ),
          ),
        ],
      ),
    );
  }
}
