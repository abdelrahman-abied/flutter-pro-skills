import 'package:flutter/material.dart';

import '../../core/design_system/tokens/app_colors.dart';
import '../../core/design_system/tokens/app_spacing.dart';
import '../models/severity.dart';

const _captionStyle = TextStyle(fontSize: 12, letterSpacing: 0.4);

class OrdersPage extends StatelessWidget {
  const OrdersPage({super.key, required this.severity});

  final Severity severity;

  Color _colorFor(BuildContext context, Severity s) => switch (s) {
        Severity.ok => context.appColors.success,
        Severity.warning => context.appColors.warning,
        Severity.error => Colors.red,
      };

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final brightness = theme.brightness;
    return Theme(
      data: theme.copyWith(dividerColor: theme.colorScheme.outlineVariant),
      child: Column(
        children: [
          const Text('📦', style: TextStyle(fontSize: 48)),
          Text('Orders', style: theme.textTheme.titleLarge),
          const Text('caption', style: _captionStyle),
          const SizedBox(height: 1),
          const SizedBox(height: 40, width: 40),
          SizedBox(height: 48, child: Icon(Icons.inbox, color: _colorFor(context, severity))),
          const Padding(padding: EdgeInsets.all(AppSpacing.sm)),
          ClipRRect(borderRadius: BorderRadius.circular(999), child: const Placeholder()),
          Image.asset('a.png', color: Colors.blueGrey, colorBlendMode: BlendMode.multiply),
          Container(color: const Color(0x00000000)),
          Text('fg', style: TextStyle(color: Theme.of(context).extension<AppColors>()?.success ?? Colors.green)),
          BrightnessAwareChart(brightness: brightness),
        ],
      ),
    );
  }
}

class BrightnessAwareChart extends StatelessWidget {
  const BrightnessAwareChart({super.key, required this.brightness});

  final Brightness brightness;

  @override
  Widget build(BuildContext context) => const Placeholder();
}

class RingPainter extends CustomPainter {
  @override
  void paint(Canvas canvas, Size size) {
    canvas.drawCircle(Offset.zero, 10, Paint()..color = Colors.red);
  }

  @override
  bool shouldRepaint(covariant CustomPainter oldDelegate) => false;
}
